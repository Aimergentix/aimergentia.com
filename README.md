# aimergentia.com

Official static website and documentation for **Aimergentia** — Human + AI Pair Software Development Studio.

## Architecture

- **Static Site Generator**: Custom Python standard-library SSG (`tools/build.py`). Zero third-party dependencies.
- **Client Runtime**: Zero client-side JavaScript (`script-src 'none'`).
- **Styling**: Single self-contained CSS stylesheet (`src/style.css`) with system typography, responsive layout rail, and verified dark-mode palette.
- **Verification Harness**: Automated unit tests (`tests/test_site.py`) validating all internal links, fragment targets, Open Graph tags, JSON-LD schemas, and mathematical WCAG AA contrast.

## Quick Start

### Build the Site
```bash
tools/build.sh
# Outputs full static distribution to dist/
```

### Run Validation Tests
```bash
tools/check.sh
# Runs build in a sandbox temp directory and executes all 17 automated tests
```

### Configure Git Pre-Commit Hooks
```bash
tools/setup.sh
```

### Verify External Links
```bash
tools/check-links.sh
```

## Page Catalog
Configured in `src/seiten.json`:
- `index.html`: Studio overview, engineering thesis, core offerings.
- `services.html`: AI-pair sprints, AI-native system architecture, codebase hardening.
- `approach.html`: Engineering methodology and deterministic guardrails.
- `stack.html`: Runtimes, frontier model routing, automated test harnesses.
- `contact.html`: Collaboration inquiries and booking.
- `privacy.html`: Static zero-tracking privacy policy.
- `terms.html`: Engagement terms and IP protection standards.
- `404.html`: Root-relative error page.

