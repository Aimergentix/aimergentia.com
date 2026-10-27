"""Technical verification of generated pages: links, structure, metadata, headers, contrast.

Tests verify the freshly built website directly. No external dependencies,
ensuring zero client-side scripts, strict CSP, and full accessibility compliance.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from build import email_ok, load_company, render, write_output

SOURCE = REPO / "src"
# tools/check.sh sets AIMERGENTIA_TEST_SITE after running build; otherwise build here.
TEST_SITE_ENV = os.environ.get("AIMERGENTIA_TEST_SITE") or os.environ.get("BB_LIMEN_TEST_SITE")
if TEST_SITE_ENV:
    ROOT = Path(TEST_SITE_ENV)
else:
    TEMP = tempfile.TemporaryDirectory(prefix="aimergentia-tests-")
    atexit.register(TEMP.cleanup)
    ROOT = Path(TEMP.name) / "site"
    write_output(render(), ROOT)

PAGES = sorted(ROOT.glob("*.html"))
CATALOG = json.loads((SOURCE / "seiten.json").read_text(encoding="utf-8"))["pages"]
BASE = "https://" + (SOURCE.parent / "public/CNAME").read_text(encoding="utf-8").strip() + "/"


def address(name: str) -> str:
    return BASE if name == "index.html" else BASE + name


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.tags: Counter[str] = Counter()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] += 1
        self.elements.append((tag, dict(attrs)))
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)
            if name == "href" and value and tag == "a":
                self.hrefs.append(value)


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


class SiteStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed = {path.name: parse_page(path) for path in PAGES}

    def test_error_page_links_work_under_nested_missing_addresses(self) -> None:
        page = self.parsed["404.html"]
        self.assertEqual(page.tags["base"], 0, "base tag would redirect relative jump links")
        missing = BASE + "some/deep/path/"
        skip = next(attrs["href"] for tag, attrs in page.elements
                    if tag == "a" and attrs.get("class") == "skip")
        self.assertEqual(urljoin(missing, skip), missing + "#content")
        for tag, attrs in page.elements:
            for key in ("href", "src"):
                value = attrs.get(key)
                if not value or value.startswith("#") or urlsplit(value).scheme:
                    continue
                with self.subTest(tag=tag, value=value):
                    self.assertTrue(value.startswith("/"))
                    target = urlsplit(urljoin(missing, value)).path.lstrip("/") or "index.html"
                    self.assertTrue((ROOT / target).is_file())

    def test_local_assets_exist(self) -> None:
        for path in PAGES:
            text = path.read_text(encoding="utf-8")
            for value in re.findall(r'(?:src|href)="([^"#]+)"', text):
                url = urlsplit(value)
                if url.scheme or url.netloc or not url.path or url.path == "/":
                    continue
                self.assertTrue((ROOT / url.path.lstrip("/")).is_file(), f"{path.name}: {value}")
            self.assertNotIn("@include", text)
            self.assertNotIn("%%", text)

    def test_scripts_are_only_the_index_json_ld_data_block(self) -> None:
        # Zero client-side JavaScript. Only structured JSON-LD data block on homepage.
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                scripts = [attrs for tag, attrs in page.elements if tag == "script"]
                expected = [{"type": "application/ld+json"}] if name == "index.html" else []
                self.assertEqual(scripts, expected)
                for _, attrs in page.elements:
                    self.assertFalse(any(key.startswith("on") for key in attrs))
                    for key in ("href", "src", "action"):
                        value = re.sub(r"[\x00-\x20]", "", attrs.get(key) or "")
                        self.assertFalse(value.lower().startswith("javascript:"))

    def test_stylesheet_is_the_single_local_file(self) -> None:
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                styles = [attrs.get("href") for tag, attrs in page.elements
                          if tag == "link" and "stylesheet" in (attrs.get("rel") or "").split()]
                self.assertEqual(styles, ["/style.css" if name == "404.html" else "style.css"])
                self.assertEqual(page.tags["style"], 0)
                self.assertFalse(any("style" in attrs for _, attrs in page.elements))

    def test_theme_colors_are_the_only_media_meta_elements(self) -> None:
        expected = [
            ("theme-color", "(prefers-color-scheme: light)"),
            ("theme-color", "(prefers-color-scheme: dark)"),
        ]
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                media_meta = [
                    attrs for tag, attrs in page.elements
                    if tag == "meta" and "media" in attrs
                ]
                self.assertEqual([(attrs.get("name"), attrs.get("media")) for attrs in media_meta], expected)
                for attrs in media_meta:
                    self.assertEqual(set(attrs), {"name", "content", "media"})
                    self.assertTrue((attrs["content"] or "").strip())

    def test_content_security_policy_keeps_the_existing_restrictions(self) -> None:
        # Strict zero-runtime CSP enforcement
        expected = {
            "default-src": ["'self'"], "img-src": ["'self'", "data:"],
            "style-src": ["'self'"], "font-src": ["'self'"],
            "script-src": ["'none'"], "object-src": ["'none'"],
            "frame-src": ["'none'"], "connect-src": ["'none'"],
            "form-action": ["'none'"], "base-uri": ["'self'"],
        }
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                policies = [attrs.get("content") for tag, attrs in page.elements
                            if tag == "meta" and (attrs.get("http-equiv") or "").lower()
                            == "content-security-policy"]
                self.assertEqual(len(policies), 1)
                directives = [part.split() for part in policies[0].split(";") if part.strip()]
                self.assertEqual(len(directives), len(expected))
                self.assertEqual({parts[0]: parts[1:] for parts in directives}, expected)

    def test_canonical_and_og_urls_follow_page_names(self) -> None:
        for path in PAGES:
            if path.name == "404.html":
                continue
            source = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                self.assertIn(f'<link rel="canonical" href="{address(path.name)}">', source)
                self.assertIn(f'<meta property="og:url" content="{address(path.name)}">', source)

    def test_each_page_has_one_main_and_one_h1(self) -> None:
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                self.assertEqual(page.tags["main"], 1)
                self.assertEqual(page.tags["h1"], 1)

    def test_search_metadata_is_present_and_nonempty(self) -> None:
        indexed = {page["file"] for page in CATALOG if page["sitemap"]}
        for name, page in self.parsed.items():
            with self.subTest(page=name):
                self.assertEqual(page.tags["title"], 1)
                source = (ROOT / name).read_text(encoding="utf-8")
                title = re.search(r"<title>(.*?)</title>", source, re.DOTALL)
                self.assertIsNotNone(title)
                self.assertTrue(title.group(1).strip())
                for property_name in ("og:title", "og:description"):
                    values = [attrs.get("content") for tag, attrs in page.elements
                              if tag == "meta" and attrs.get("property") == property_name]
                    self.assertEqual(len(values), 1)
                    self.assertTrue((values[0] or "").strip())
                if name in indexed:
                    descriptions = [attrs.get("content") for tag, attrs in page.elements
                                    if tag == "meta" and attrs.get("name") == "description"]
                    self.assertEqual(len(descriptions), 1)
                    self.assertTrue((descriptions[0] or "").strip())

    def test_generated_sitemap_and_robots_follow_catalog(self) -> None:
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        sitemap = ElementTree.parse(ROOT / "sitemap.xml").getroot()
        self.assertEqual(sitemap.tag, namespace + "urlset")
        actual = []
        for entry in sitemap:
            self.assertEqual(entry.tag, namespace + "url")
            locations = entry.findall(namespace + "loc")
            dates = entry.findall(namespace + "lastmod")
            self.assertEqual(len(locations), 1)
            self.assertEqual(len(dates), 1)
            date.fromisoformat(dates[0].text)
            actual.append((locations[0].text, dates[0].text))
        expected = [(address(page["file"]), page["lastmod"])
                    for page in CATALOG if page["sitemap"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len({location for location, _ in actual}), len(actual))
        declarations = re.findall(r"(?im)^Sitemap:\s*(\S+)\s*$",
                                  (ROOT / "robots.txt").read_text(encoding="utf-8"))
        self.assertIn(BASE + "sitemap.xml", declarations)

    def test_internal_links_and_fragments_exist(self) -> None:
        for source_name, page in self.parsed.items():
            for href in page.hrefs:
                target = urlsplit(href)
                if target.scheme or target.netloc or href.startswith(("mailto:", "tel:")):
                    continue
                target_name = "index.html" if target.path == "/" else target.path.lstrip("/") or source_name
                target_path = ROOT / target_name
                with self.subTest(source=source_name, href=href):
                    self.assertTrue(target_path.is_file(), f"Target file missing for {href}")
                    if target.fragment:
                        self.assertIn(target.fragment, self.parsed[target_name].ids)

    def test_mail_and_phone_targets_are_complete(self) -> None:
        for name, page in self.parsed.items():
            for href in page.hrefs:
                with self.subTest(page=name, href=href):
                    if href.startswith("mailto:"):
                        self.assertTrue(email_ok(href.removeprefix("mailto:").split("?")[0]))
                    elif href.startswith("tel:"):
                        self.assertRegex(href, r"^tel:(?:\+[1-9]\d{1,14}|\d{3,6})$")

    def test_json_ld_is_valid_and_claims_no_business_location(self) -> None:
        for path in PAGES:
            scripts = re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                path.read_text(encoding="utf-8"),
                re.DOTALL,
            )
            for script in scripts:
                data = json.loads(script)
                self.assertEqual([node["@type"] for node in data["@graph"]],
                                 ["Organization", "WebSite"])
                for forbidden in ("LocalBusiness", "LegalService"):
                    self.assertNotIn(forbidden, json.dumps(data))
                for forbidden in ("aggregateRating", '"review"'):
                    self.assertNotIn(forbidden, json.dumps(data))

    def test_legal_links_are_on_every_page(self) -> None:
        for path in PAGES:
            text = path.read_text(encoding="utf-8")
            for target, label in (("privacy.html", "Privacy"), ("terms.html", "Terms")):
                with self.subTest(page=path.name, link=label):
                    prefix = "/" if path.name == "404.html" else ""
                    self.assertGreaterEqual(text.count(f'<a href="{prefix}{target}">{label}</a>'), 2)

    def test_noindex_and_sitemap_agree(self) -> None:
        in_sitemap = {page["file"] for page in CATALOG if page["sitemap"]}
        for name, page in self.parsed.items():
            robots = [attrs.get("content") for tag, attrs in page.elements
                      if tag == "meta" and attrs.get("name") == "robots"]
            with self.subTest(page=name):
                self.assertEqual(robots, [] if name in in_sitemap else ["noindex"])

    def test_contact_literals_are_not_maintained_in_templates(self) -> None:
        live = load_company(REPO)
        values = (live["email"], live["email_privacy"])
        for path in [*(SOURCE / "pages").glob("*.html"), *(SOURCE / "partials").glob("*.html")]:
            text = path.read_text(encoding="utf-8")
            for value in values:
                with self.subTest(path=path.name, value=value):
                    self.assertNotIn(value, text)


# WCAG AA text contrast requirement: 4.5:1 minimum
AA_TEXT = 4.5

PAIRS = [
    ("--ink", "--paper"),
    ("--body", "--paper"),
    ("--muted", "--paper"),
    ("--accent-ink", "--paper"),
    ("--accent", "--paper"),
    ("--gut-ink", "--paper"),
    ("--body", "--surface"),
    ("--muted", "--surface"),
    ("--accent-ink", "--surface"),
    ("--accent", "--surface"),
    ("--gut-ink", "--gut-flaeche"),
    ("--on-carrier", "--carrier"),
    ("--meta-on-carrier", "--carrier"),
    ("--link-ink", "--paper"),
    ("--link-ink", "--surface"),
    ("--link-on-carrier", "--carrier"),
    ("--accent-on-carrier", "--carrier"),
    ("--brand-leaf", "--carrier"),
    ("--leicht-ink", "--paper"),
    ("--leicht-ink", "--surface"),
    ("--st-1", "--surface"),
    ("--st-2", "--surface"),
    ("--st-3", "--surface"),
    ("--st-4", "--surface"),
    ("--st-5", "--surface"),
    ("--paper", "--accent"),
    ("--carrier", "--accent-on-carrier"),
    ("--carrier", "--link-on-carrier"),
    ("--carrier", "--on-carrier"),
    ("--ink", "--surface"),
    ("--body", "--gut-flaeche"),
    ("--ink", "--hauch"),
    ("--body", "--hauch"),
    ("--muted", "--hauch"),
    ("--accent-ink", "--hauch"),
    ("--link-ink", "--hauch"),
]


def block(text: str, start: str) -> str:
    i = text.index(start) + len(start)
    depth, j = 1, i
    while depth:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    return text[i : j - 1]


def colors(text: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", text))


def palette(dark: bool) -> dict[str, str]:
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    values = colors(block(css, ":root {"))
    if dark:
        values.update(colors(block(css[css.index("prefers-color-scheme: dark") :], ":root {")))
    return values


def luminance(hex_value: str) -> float:
    h = hex_value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(front: str, back: str) -> float:
    a, b = luminance(front), luminance(back)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


class ContrastTests(unittest.TestCase):
    def test_all_pairs_meet_wcag_aa(self) -> None:
        for mode, dark in (("light", False), ("dark", True)):
            values = palette(dark)
            for front, back in PAIRS:
                with self.subTest(mode=mode, front=front, back=back):
                    self.assertIn(front, values, f"{front} missing in PALETTE block")
                    self.assertIn(back, values, f"{back} missing in PALETTE block")
                    ratio = contrast(values[front], values[back])
                    self.assertGreaterEqual(
                        ratio, AA_TEXT,
                        f"{front} on {back} ({mode}) gives {ratio:.2f}:1, required {AA_TEXT}:1"
                    )


if __name__ == "__main__":
    unittest.main()
