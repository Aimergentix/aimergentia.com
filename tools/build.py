"""Static site generator for aimergentia.com.

Standard library Python only (no external dependencies).
Reads templates and partials from src/ and assets from public/,
validating all links, tokens, and schemas before updating dist/.
"""
from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from urllib.parse import urlsplit, urljoin

ROOT = Path(__file__).resolve().parents[1]
PARTIALS = ("head", "skip", "rail", "foot")
INCLUDE = re.compile(r"<!-- @include ([a-z-]+) -->\n?")
CURRENT = re.compile(r"%%CUR-([a-z0-9-]+)%%")
COMPANY_TOKEN = re.compile(r"%%COMPANY:([a-z0-9_.-]+)%%")
COMPANY_JSON = re.compile(r'"%%COMPANY_JSON:([a-z0-9_.-]+)%%"')
JSON_SCRIPT = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
REQUIRED_COMPANY_KEYS = {
    "name",
    "tagline",
    "description",
    "email",
    "email_privacy",
    "github",
    "location",
    "founded",
}


# ---------------------------------------------------------------- Inputs & Validation

def read_source(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"{path}: file missing")
    data = path.read_bytes()
    if not data:
        raise ValueError(f"{path}: file is empty")
    return data


def load_json(path: Path) -> object:
    try:
        return json.loads(read_source(path))
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None


def single_line(value: str) -> bool:
    """Ensure no control characters or line/paragraph separators (e.g. U+2028)."""
    return not any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in value)


def text_ok(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and single_line(value)
        and "%%" not in value
    )


def email_ok(value: object) -> bool:
    return text_ok(value) and bool(
        re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", str(value))
    )


def url_ok(value: object) -> bool:
    return text_ok(value) and bool(re.fullmatch(r"https?://[^\s]+", str(value)))


def require_keys(value: object, keys: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{field}: expected keys: {', '.join(sorted(keys))}")


def load_catalog(root: Path) -> dict:
    path = root / "src/seiten.json"
    catalog = load_json(path)
    require_keys(catalog, {"pages", "public_files"}, str(path))
    names = []
    for page in catalog["pages"]:
        name = page.get("file") if isinstance(page, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.html", name):
            raise ValueError(f"{path}: invalid page entry {page!r}")
        if type(page.get("sitemap")) is not bool:
            raise ValueError(f"{path}: {name}: sitemap must be true or false")
        if page["sitemap"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(page.get("lastmod"))):
            raise ValueError(f"{path}: {name}: lastmod must be YYYY-MM-DD")
        names.append(name)
    if len(names) != len(set(names)) or not {"index.html", "404.html"} <= set(names):
        raise ValueError(f"{path}: duplicate pages or missing index.html/404.html")
    public = catalog["public_files"]
    if (
        not isinstance(public, list)
        or "CNAME" not in public
        or not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", name) for name in public)
    ):
        raise ValueError(f"{path}: public_files must contain valid filenames including CNAME")
    return catalog


def base_url(root: Path) -> str:
    return "https://" + read_source(root / "public/CNAME").decode("utf-8").strip() + "/"


def load_company(root: Path) -> dict:
    name = "company.json"
    data = load_json(root / "src" / name)
    require_keys(data, REQUIRED_COMPANY_KEYS, name)
    for key in ("name", "tagline", "description", "location", "founded"):
        if not text_ok(data[key]):
            raise ValueError(f"{name}: {key}: expected non-empty single-line string")
    if not email_ok(data["email"]) or not email_ok(data["email_privacy"]):
        raise ValueError(f"{name}: invalid email address")
    if not url_ok(data["github"]):
        raise ValueError(f"{name}: invalid github url")
    return data


# ---------------------------------------------------------------- Token Substitution

def company_values(data: dict) -> dict[str, str]:
    """Generates all %%COMPANY:...%% replacement values."""
    values = {}
    for key, val in data.items():
        if isinstance(val, str):
            values[key] = val
        elif isinstance(val, dict):
            for sub_k, sub_v in val.items():
                if isinstance(sub_v, str):
                    values[f"{key}.{sub_k}"] = sub_v
    return values


def json_value(value: object) -> str:
    """Escapes JSON string to prevent </script> injection."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_company(source: str, data: dict) -> str:
    values = company_values(data)

    def replace(match: re.Match) -> str:
        if match[1] not in values:
            raise ValueError(f"Unknown company token: {match[0]}")
        return escape(values[match[1]], quote=True)

    def replace_script(match: re.Match) -> str:
        def replace_json(token: re.Match) -> str:
            if token[1] not in values:
                raise ValueError(f"Unknown JSON-LD company token: {token[0]}")
            return json_value(values[token[1]])

        body = COMPANY_JSON.sub(replace_json, match[2])
        if "%%COMPANY" in body:
            raise ValueError("JSON-LD requires complete company JSON tokens")
        json.loads(body)
        return match[1] + body + match[3]

    result = COMPANY_TOKEN.sub(replace, JSON_SCRIPT.sub(replace_script, source))
    if "%%COMPANY" in result:
        raise ValueError("Invalid company placeholder remaining")
    return result


# ---------------------------------------------------------------- Page Assembly

def error_page_links(source: str) -> str:
    """Ensures relative asset/navigation links on 404.html are absolute from root."""
    offsets = [0]
    for line in source.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    replacements = []

    def replace(match: re.Match) -> str:
        value = match[3]
        url = urlsplit(value)
        if url.scheme or url.netloc or not url.path or value.startswith("/") or value.startswith("#"):
            return match[0]
        return match[1] + match[2] + urljoin("/", value) + match[2]

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text()
            updated = re.sub(r'''(\b(?:href|src)\s*=\s*)(["'])(.*?)\2''', replace, raw)
            if raw != updated:
                line, column = self.getpos()
                start = offsets[line - 1] + column
                if source[start:start + len(raw)] != raw:
                    raise ValueError(f"404.html:{line}: unable to anchor link unambiguously")
                replacements.append((start, start + len(raw), updated))

    parser = Links(convert_charrefs=False)
    parser.feed(source)
    parser.close()
    for start, end, updated in reversed(replacements):
        source = source[:start] + updated + source[end:]
    return source


def sitemap(pages: list[dict], base: str) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in pages:
        if page["sitemap"]:
            url = base + ("" if page["file"] == "index.html" else page["file"])
            lines.extend([
                "  <url>",
                f"    <loc>{url}</loc>",
                f"    <lastmod>{page['lastmod']}</lastmod>",
                "  </url>",
            ])
    return ("\n".join([*lines, "</urlset>"]) + "\n").encode("utf-8")


def assemble(path: Path, source: str, partials: dict[str, str]) -> str:
    """Injects layout partials in strict predefined order."""
    output = []
    seen = []
    for number, line in enumerate(source.splitlines(keepends=True), 1):
        match = INCLUDE.fullmatch(line)
        if match:
            name = match[1]
            if len(seen) >= len(PARTIALS) or name != PARTIALS[len(seen)]:
                raise ValueError(
                    f"{path}:{number}: unknown, duplicate or out-of-order include '{name}' "
                    f"(expected '{PARTIALS[len(seen)] if len(seen) < len(PARTIALS) else 'none'}')"
                )
            seen.append(name)
            output.append(f"<!-- #{name} -->\n{partials[name]}<!-- /#{name} -->\n")
        else:
            if "@include" in line:
                raise ValueError(f"{path}:{number}: include must occupy its own line")
            output.append(line)
    if tuple(seen) != PARTIALS:
        raise ValueError(f"{path}: missing includes; required sequence: {', '.join(PARTIALS)}")
    return "".join(output)


def render(root: Path = ROOT) -> dict[str, bytes]:
    catalog = load_catalog(root)
    company = load_company(root)
    pages = catalog["pages"]
    names = {page["file"] for page in pages}

    # Verify all expected directories match exactly
    for directory, expected in (
        (root / "src/pages", names),
        (root / "src/partials", {f"{name}.html" for name in PARTIALS}),
        (root / "public", set(catalog["public_files"])),
    ):
        actual = {path.name for path in directory.iterdir()} if directory.is_dir() else set()
        if actual != expected:
            raise ValueError(
                f"{directory}: missing {sorted(expected - actual)}, unexpected {sorted(actual - expected)}"
            )

    partials = {name: read_source(root / "src/partials" / f"{name}.html").decode("utf-8") for name in PARTIALS}
    base = base_url(root)
    result = {}

    for page in pages:
        path = root / "src/pages" / page["file"]
        text = assemble(path, read_source(path).decode("utf-8"), partials)
        for match in CURRENT.finditer(text):
            if match[1] + ".html" not in names:
                raise ValueError(f"{path}: unknown navigation target '{match[1]}'")
        text = CURRENT.sub(lambda match: ' aria-current="page"' if match[1] + ".html" == page["file"] else "", text)
        text = render_company(text, company)
        if page["file"] == "404.html":
            text = error_page_links(text)
        result[page["file"]] = text.encode("utf-8")

    result["style.css"] = read_source(root / "src/style.css")
    result["sitemap.xml"] = sitemap(pages, base)
    for name in catalog["public_files"]:
        result[name] = read_source(root / "public" / name)
    return result


# ---------------------------------------------------------------- Output Writing

def write_output(files: dict[str, bytes], output: Path, root: Path = ROOT) -> None:
    """Atomic write to temporary directory before swapping to target directory."""
    output = output.resolve()
    if output.exists() and output != (root / "dist").resolve():
        raise ValueError(f"{output}: will not overwrite existing directory outside dist/")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build.", dir=output.parent) as temp:
        stage = Path(temp) / "new"
        stage.mkdir()
        for name, data in files.items():
            (stage / name).write_bytes(data)
        old = Path(temp) / "old"
        if output.exists():
            output.rename(old)
        try:
            stage.rename(output)
        except OSError:
            if old.exists():
                old.rename(output)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Output directory (default: dist/)")
    args = parser.parse_args()
    try:
        files = render()
        write_output(files, args.output)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Generated: {len(files)} files in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
