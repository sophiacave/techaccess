<!-- mcp-name: io.github.sophiacave/techaccess -->
# TechAccess

[![CI](https://github.com/sophiacave/techaccess/actions/workflows/ci.yml/badge.svg)](https://github.com/sophiacave/techaccess/actions/workflows/ci.yml)


AI-powered accessibility toolkit. WCAG audits, code fix generation, alt text evaluation, and structured reports — powered by local AI.

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

# AI-enhanced audit (semantic analysis via Ollama)
techaccess audit https://example.com --ai

# Generate code fixes for accessibility issues
techaccess fix https://example.com

# Evaluate alt text quality
techaccess evaluate https://example.com

# ARIA accessibility tree snapshot
techaccess snapshot https://example.com

# Contrast ratio check
techaccess contrast https://example.com
```

### Output Formats

```bash
# JSON, Markdown, SARIF (GitHub Code Scanning), or HTML report
techaccess audit https://example.com -f html -o report.html
techaccess audit https://example.com -f sarif -o results.sarif

# CI mode — exit code 1 on serious+ issues
techaccess audit https://example.com --fail-on serious
```

## MCP Server

```bash
# Add to Claude
claude mcp add techaccess -- python /path/to/server.py
```

Tools: `access_audit`, `access_fix`, `access_evaluate`, `access_snapshot`, `access_contrast`, `access_alttext`

## How It Works

TechAccess combines three layers:

1. **axe-core** — industry-standard WCAG 2.0/2.1/2.2 rule engine
2. **Playwright ARIA** — captures the full accessibility tree for semantic analysis
3. **AI layer** — local models (Ollama) or Claude API for:
   - Semantic ARIA analysis (landmark structure, heading hierarchy, focus order)
   - Alt text generation and evaluation (llava for vision)
   - Code remediation with before/after diffs
   - Contextual fix suggestions

### Scoring

0-100 score with letter grade (A+ through F). Weighted by severity: critical issues count 4x more than minor ones.

### Reports

- **JSON** — machine-readable, CI/CD integration
- **Markdown** — human-readable summaries
- **SARIF** — GitHub Code Scanning compatible
- **HTML** — dark-themed dashboard with charts and fix previews

## Requirements

- Python 3.10+
- Chromium (installed via Playwright)
- Optional: [Ollama](https://ollama.com) for local AI features

## License

MIT. Free forever.
