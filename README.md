# TechAccess

AI-powered accessibility toolkit. WCAG audits, ARIA tree analysis, contrast checking, and structured reports.

Built by [Like One Foundation](https://likeone.ai) — because accessibility shouldn't require a six-figure budget.

## Install

```bash
pip install techaccess
playwright install chromium
```

## CLI

```bash
# Full WCAG audit with score
techaccess audit https://example.com

# ARIA accessibility tree
techaccess snapshot https://example.com

# Contrast ratio check
techaccess contrast https://example.com
```

## MCP Server

```bash
# Add to Claude
claude mcp add techaccess -- python /path/to/server.py
```

Tools: `access_audit`, `access_snapshot`, `access_contrast`

## How It Works

TechAccess combines three layers:
1. **axe-core** — industry-standard rule engine (WCAG 2.0/2.1/2.2)
2. **ARIA snapshots** — Playwright captures the full accessibility tree
3. **Scoring engine** — 0-100 score with letter grade (A+ through F)

Output formats: JSON, Markdown, SARIF (GitHub Code Scanning)

## License

MIT. Free forever.
