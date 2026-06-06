# TechAccess Architecture — Research-Backed Plan
## AI-Powered Accessibility Toolkit
### Like One Foundation | Sprint #57 | June 6, 2026

---

## Vision

TechAccess doesn't just find accessibility problems — it understands them and fixes them.

Every existing tool detects issues. None remediate with AI. That's the product.

---

## Market Context (Verified Research, 3 Agents)

- **Market**: $1.75B digital accessibility market (2026). Remediation segment: 29% CAGR.
- **Problem**: Automated tools catch only **31% of WCAG 2.2 AA** (17 of 55 criteria).
- **Lawsuits**: 5,100+ ADA digital suits in 2025 (37% surge). 94.8% of websites fail.
- **EU**: European Accessibility Act enforced June 2025. Fines up to 4% revenue.
- **Fix cost**: $25 in development vs $2,500+ in production. Shift-left is the opportunity.
- **Overlays**: Dead approach. FTC fined accessiBe $1M. 800+ overlay users sued.
- **Enterprise tools**: $25K-$250K/year. Inaccessible to 99% of organizations.
- **Gap**: No open source AI-native accessibility toolkit with remediation exists.

---

## Competitive Landscape

### Detection Tools (Where axe-core wins)
- **axe-core**: 4B+ downloads. ~57% automated detection. Open source. OUR FOUNDATION.
- **a11ymcp**: 8K downloads, MCP server for accessibility. Detection only. No auto-fix.
- **WAVE**: Free browser extension. Visual overlay. One page at a time.
- **Lighthouse**: Built into Chrome. Scores 0-100. ~30-40% WCAG coverage.
- **Pa11y**: Open source CLI. Rule-based.

### Enterprise (What we democratize)
- **Deque**: $40/user/mo to $250K/yr. axe-core + guided tests.
- **Level Access**: $25K-$150K/yr + $50K-$200K managed services.
- **Siteimprove**: $15K-$150K/yr. Agentic AI content platform.

### Alt Text (Where AI is needed)
- **AltText.ai**: GPT Vision + Claude. $5/mo+. No page context awareness.
- **AutoAlt.ai**: GPT + Gemini. EU-focused. Same context gap.
- **Gap**: No tool evaluates alt text QUALITY. No tool understands page context.

### Document (Future phase)
- **PREP**: 95% auto-tagging accuracy. Cents/page. 5-20% human review.
- **Equidox**: Computer vision for PDF tagging. Enterprise pricing.
- **veraPDF**: Open source validation only.

---

## Core Innovation

### The Pipeline Nobody Has Built

```
1. CAPTURE
   Playwright -> page.ariaSnapshot() -> full ARIA accessibility tree (YAML)
   + axe-core scan -> rule-based violations (JSON)
   + screenshot -> visual layout (PNG)

2. ANALYZE (AI Layer)
   Feed ARIA tree + axe violations + screenshot to LLM
   -> Semantic understanding of page intent
   -> Issues that rules can't catch (the missing 69%)
   -> Context-aware evaluation of existing alt text
   -> Cognitive complexity assessment

3. REMEDIATE (AI Layer)
   For each issue, generate:
   -> Corrected HTML/ARIA code (diff format)
   -> Alt text with page context
   -> WCAG-compliant color alternatives
   -> Heading structure corrections
   -> ARIA attribute recommendations

4. REPORT
   -> JSON (CI/CD), SARIF (GitHub), HTML (dashboard), Markdown (PR comments)
   -> Score 0-100 with letter grade
   -> Before/after code diffs
```

**Key differentiator**: Every other tool stops at step 1 or 2. We do all 4.

---

## Architecture Layers

```
techaccess/
├── scanner/
│   ├── aria.py          # Playwright ARIA snapshot capture
│   ├── axe.py           # axe-core integration (@axe-core/playwright)
│   ├── visual.py        # Screenshot capture for vision analysis
│   └── keyboard.py      # Keyboard navigation audit (future)
│
├── analyzer/
│   ├── rules.py         # Extended rule-based checks (lo-eyes heritage)
│   ├── semantic.py      # AI semantic analysis of ARIA tree
│   ├── alttext.py       # AI alt text evaluation + generation
│   └── contrast.py      # Contrast analysis + fix suggestions
│
├── remediator/
│   ├── codegen.py       # AI-generated HTML/ARIA fixes
│   ├── diff.py          # Generate apply-able diffs
│   └── suggestions.py   # Human-readable fix descriptions
│
├── reporter/
│   ├── json_report.py   # Machine-readable JSON
│   ├── sarif.py         # GitHub Code Scanning format
│   ├── html_report.py   # Visual dashboard
│   ├── markdown.py      # PR comment format
│   └── score.py         # 0-100 scoring engine
│
├── server.py            # MCP server (FastMCP)
├── cli.py               # CLI interface
└── models.py            # AI model abstraction (Ollama / Claude / OpenAI)
```

---

## AI Model Strategy

**Design principle**: Local-first. Every feature works offline with Ollama.
Cloud models optional for higher accuracy. User chooses.

| Use Case | Local (Ollama) | Cloud (Claude) | Accuracy Target |
|----------|----------------|-----------------|-----------------|
| ARIA tree analysis | qwen3:30b | Sonnet 4.6 | 85%+ |
| Alt text generation | llava:13b | Claude Vision | 90%+ |
| Alt text evaluation | qwen3:30b | Sonnet 4.6 | 80%+ |
| Code remediation | qwen3:30b | Sonnet 4.6 | 70%+ clean apply |
| Contrast suggestions | Rule-based | Rule-based | 100% |
| Cognitive assessment | qwen3:14b | Haiku 4.5 | Experimental |

---

## MCP Server Tools

```python
# Core tools
access_audit(url, wcag_level="AA", viewports=["mobile","desktop"])
  -> Full WCAG audit with axe-core + AI analysis + scoring

access_fix(url, issues=None)
  -> AI-generated code fixes as diffs

access_alttext(image_url, context="")
  -> Context-aware alt text generation

access_evaluate_alt(url)
  -> Evaluate quality of existing alt text on page

access_snapshot(url)
  -> Raw ARIA accessibility tree (YAML)

access_contrast(url)
  -> Color contrast analysis with WCAG-compliant alternatives

access_report(url, format="json")
  -> Comprehensive accessibility report
```

---

## CLI Interface

```bash
techaccess audit https://example.com          # Full audit + grade
techaccess fix https://example.com            # Generate code fixes
techaccess alttext ./image.png --context "..." # Generate alt text
techaccess evaluate https://example.com       # Evaluate existing alt text
techaccess snapshot https://example.com       # ARIA tree dump
techaccess contrast https://example.com       # Contrast check
techaccess report https://example.com -f html # HTML report
techaccess ci https://example.com --fail-on high  # CI mode (exit codes)
```

---

## WCAG 2.2 AA Coverage Target

### Automated (axe-core baseline: 17 criteria)
All criteria that axe-core covers, plus our extended checks from lo-eyes.

### AI-Enhanced (TechAccess adds: 8-12 criteria)
- 1.1.1 Alt text quality evaluation (not just detection)
- 1.3.1 Meaningful sequence in SPAs (reading order inference)
- 1.4.1 Use of color (AI vision analysis)
- 2.4.4 Link purpose in context (semantic evaluation)
- 2.4.6 Headings/labels quality (beyond structure check)
- 3.1.2 Language of parts (AI language detection)
- 3.2.6 Consistent help (cross-page pattern analysis)
- 3.3.7 Redundant entry (form flow analysis)

**Target**: 25+ of 55 AA criteria (45%+) — up from industry standard 31%.

### Human-Required (flagged with guidance)
Remaining criteria flagged with clear human testing instructions.

---

## Build Phases

### Phase 1: Foundation (2-3 sprints)
Goal: Working scanner + rule engine + CLI + MCP server
- [ ] Project scaffolding (pyproject.toml, tests, CI)
- [ ] axe-core integration via Playwright
- [ ] ARIA snapshot capture (page.ariaSnapshot())
- [ ] Extended rule-based checks (from lo-eyes, expanded)
- [ ] Scoring engine (0-100 + letter grade)
- [ ] CLI: `audit`, `snapshot`, `contrast` commands
- [ ] MCP server: `access_audit`, `access_snapshot`
- [ ] JSON + Markdown reporters
- [ ] 30+ tests
- [ ] GitHub repo + MIT license + FUNDING.yml
- [ ] README with clear positioning

### Phase 2: AI Layer (2-3 sprints)
Goal: AI analysis + alt text + remediation
- [ ] Ollama integration (local-first AI)
- [ ] ARIA tree AI analysis (semantic issues)
- [ ] Alt text generation (llava / Claude Vision)
- [ ] Alt text quality evaluation
- [ ] Code remediation engine (generate HTML diffs)
- [ ] Contrast fix suggestions
- [ ] HTML report generator
- [ ] SARIF output (GitHub Code Scanning)
- [ ] CLI: `fix`, `alttext`, `evaluate` commands
- [ ] MCP: `access_fix`, `access_alttext`, `access_evaluate_alt`
- [ ] Cloud model support (Claude API, OpenAI)

### Phase 3: Integration + Scale (2-3 sprints)
Goal: CI/CD, PyPI, monitoring
- [ ] GitHub Actions workflow
- [ ] CI mode with configurable thresholds
- [ ] PyPI publication
- [ ] Multi-page site crawl
- [ ] Accessibility monitoring (scheduled scans)
- [ ] npm wrapper package
- [ ] Documentation site

### Phase 4: Advanced (future)
- [ ] PDF/document accessibility conversion
- [ ] Keyboard navigation audit (automated tab-through)
- [ ] Screen reader simulation
- [ ] Color blindness simulation
- [ ] Cognitive complexity scoring
- [ ] VS Code extension
- [ ] REST API (FastAPI)

---

## Technical Stack

- **Language**: Python 3.10+
- **Browser**: Playwright (async)
- **Rule engine**: axe-core (via @axe-core/playwright or direct injection)
- **AI local**: Ollama (llava, qwen3, mxbai-embed-large)
- **AI cloud**: Claude API (optional), OpenAI API (optional)
- **MCP**: FastMCP (mcp[cli])
- **Package**: hatchling -> PyPI
- **Testing**: pytest + playwright fixtures
- **CI**: GitHub Actions
- **Reports**: Jinja2 (HTML), json, SARIF spec

---

## Sustainability Model (NVDA Precedent)

NVDA (NV Access) built the leading open source screen reader:
- 250,000+ users, 175 countries, 55+ languages
- Funded by donations + grants (Microsoft is a major backer)
- Nonprofit structure

**TechAccess model:**
- **Free forever**: Open source core, CLI, MCP server, local AI
- **GitHub Sponsors**: Individual + corporate sponsors
- **Grants**: AWS Imagine (submitted), NSF SBIR, others
- **Pro tier** (future): Cloud AI, monitoring, multi-site, API access
- **Consulting**: Custom rules, compliance reports, training
- **Nonprofit discount**: Free Pro for 501(c)(3) orgs

---

## Success Metrics (Year 1)

| Metric | Target |
|--------|--------|
| WCAG criteria covered | 25+ of 55 AA (45%+) |
| Audit speed | < 30 seconds per page |
| Alt text accuracy | 4+/5 human-rated |
| Fix apply rate | 70%+ of diffs apply cleanly |
| GitHub stars | 500+ |
| PyPI downloads | 5,000+ |
| Organizations using | 50+ |
| Community contributors | 10+ |

---

## Why TechAccess Wins

1. **AI-native**: Not AI bolted onto rules. AI IS the core engine.
2. **Remediation**: Every other tool says "you have a problem." We say "here's the fix."
3. **Context-aware**: Alt text that understands the page, not just the image.
4. **Open source**: Free forever. No $250K enterprise lock-in.
5. **Local-first**: Works offline with Ollama. Privacy by design.
6. **MCP-native**: Built for the AI agent ecosystem from day one.
7. **Built by disabled**: Not corporate compliance. Genuine lived experience.
8. **Anti-overlay**: We fix source code. We don't add runtime patches.

---

*Built with love by Like One Foundation.*
*Because accessibility shouldn't require a six-figure budget.*
*And because the people who need accessible tools the most*
*are the last ones the industry builds for.*
