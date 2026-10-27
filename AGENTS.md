# Autonomous Agent Guidelines — Aimergentia

This repository hosts the static website and verification harness for **Aimergentia** (`aimergentia.com`), an engineering studio specializing in AI-pair software development.

All autonomous agents and human contributors must adhere to these governing rules.

---

## 1. Technical Invariants

* **R-TECH-1 (Zero Client-Side JavaScript):**
  No client-side runtime JavaScript is permitted. The Content Security Policy enforces `script-src 'none'`. The only allowed `<script>` tag is the structured `<script type="application/ld+json">` metadata block on `index.html`.
* **R-TECH-2 (Standard Library Only):**
  The site generator (`tools/build.py`) must rely strictly on the Python standard library. No third-party packages or framework dependencies may be introduced.
* **R-TECH-3 (Strict Security Headers):**
  Do not weaken the Content Security Policy meta tag in `src/partials/head.html`. All fonts, images, and stylesheets must be self-hosted and local.

---

## 2. Quality & Accessibility

* **R-PERF-1 (Sub-millisecond Performance):**
  Pages must be pre-rendered HTML and CSS. No dynamic hydration, no tracking beacons, no external font requests.
* **R-A11Y-1 (WCAG AA Contrast):**
  All foreground and background color combinations in `src/style.css` must pass WCAG AA contrast (minimum 4.5:1 ratio) in both light and dark modes. Verified automatically in `tests/test_site.py`.
* **R-A11Y-2 (Semantic HTML):**
  Every page must feature exactly one `<main>` landmark with `id="content"` and exactly one `<h1>`.

---

## 3. Editorial & Content

* **R-CONTENT-1 (Substance Over Hype):**
  Content must remain technical, concrete, and verifiable. Avoid unsubstantiated tech marketing cliches ("revolutionizing", "disrupting", "unmatched"). Describe exact architectures, latency profiles, testing loops, and model pairing dynamics.
* **R-CONTENT-2 (Machine Discoverability):**
  Keep `public/llms.txt`, Open Graph metadata, and JSON-LD schemas in sync with all live pages.

---

## 4. Verification & Testing

* **R-TEST-1 (Mandatory Green Suite):**
  Before any commit or deployment, `tools/check.sh` must execute and pass completely:
  ```bash
  tools/check.sh
  ```
* **R-TEST-2 (Pre-Commit Enforcement):**
  Pre-commit hooks configured via `tools/setup.sh` execute `tools/check.sh` automatically on git commit.

