"""TechAccess Scanner — Playwright + axe-core + ARIA snapshot engine.

Captures three complementary views of a page's accessibility:
1. axe-core violations (rule-based, industry standard)
2. ARIA accessibility tree (semantic structure)
3. Extended DOM checks (from lo-eyes heritage)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

AXE_JS = (Path(__file__).parent / "axe.min.js").read_text()

VIEWPORTS = {
    "mobile": {"width": 375, "height": 667, "is_mobile": True},
    "tablet": {"width": 768, "height": 1024, "is_mobile": True},
    "desktop": {"width": 1440, "height": 900, "is_mobile": False},
}


@dataclass
class Issue:
    """A single accessibility issue."""
    rule_id: str
    wcag: str  # e.g. "1.1.1"
    impact: str  # critical, serious, moderate, minor
    description: str
    help_url: str = ""
    element_html: str = ""
    selector: str = ""
    viewport: str = ""
    source: str = "axe-core"  # axe-core | dom-check | aria-analysis


@dataclass
class ScanResult:
    """Complete scan result for a single URL."""
    url: str
    timestamp: str
    issues: list[Issue] = field(default_factory=list)
    aria_tree: dict = field(default_factory=dict)
    axe_summary: dict = field(default_factory=dict)
    viewports_tested: list[str] = field(default_factory=list)
    scan_time_ms: int = 0

    @property
    def violation_count(self) -> int:
        return len(self.issues)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.impact == "critical")

    @property
    def serious_count(self) -> int:
        return sum(1 for i in self.issues if i.impact == "serious")

    def issues_by_impact(self) -> dict[str, list[Issue]]:
        result: dict[str, list[Issue]] = {}
        for issue in self.issues:
            result.setdefault(issue.impact, []).append(issue)
        return result

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "timestamp": self.timestamp,
            "scan_time_ms": self.scan_time_ms,
            "viewports_tested": self.viewports_tested,
            "summary": {
                "total": self.violation_count,
                "critical": self.critical_count,
                "serious": self.serious_count,
                "moderate": sum(1 for i in self.issues if i.impact == "moderate"),
                "minor": sum(1 for i in self.issues if i.impact == "minor"),
            },
            "issues": [
                {
                    "rule_id": i.rule_id,
                    "wcag": i.wcag,
                    "impact": i.impact,
                    "description": i.description,
                    "help_url": i.help_url,
                    "element": i.element_html[:200] if i.element_html else "",
                    "selector": i.selector,
                    "viewport": i.viewport,
                    "source": i.source,
                }
                for i in self.issues
            ],
            "axe_summary": self.axe_summary,
        }


CLIPPING_CHECK_JS = """() => {
    const vw = window.innerWidth;
    const issues = [];
    document.querySelectorAll('*').forEach(el => {
        const cs = getComputedStyle(el);
        if (cs.overflowX !== 'hidden') return;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0) return;
        // Check if any child extends beyond this element
        for (const child of el.children) {
            const cr = child.getBoundingClientRect();
            if (cr.width <= 0) continue;
            if (cr.right > rect.right + 2 || cr.left < rect.left - 2) {
                const tag = el.tagName.toLowerCase();
                const cls = el.className ? '.' + String(el.className).split(' ')[0] : '';
                const childTag = child.tagName.toLowerCase();
                const childCls = child.className ? '.' + String(child.className).split(' ')[0] : '';
                const clippedPx = Math.round(Math.max(0, cr.right - rect.right));
                if (clippedPx > 10) {
                    issues.push({
                        parent: `${tag}${cls}`,
                        child: `${childTag}${childCls}`,
                        clipped_px: clippedPx,
                        parent_width: Math.round(rect.width),
                        child_width: Math.round(cr.width),
                        html: el.outerHTML.substring(0, 150),
                    });
                }
                break;
            }
        }
    });
    return issues.slice(0, 20);
}"""


def _extract_wcag(tags: list[str]) -> str:
    """Extract WCAG criterion from axe-core tags like 'wcag111' -> '1.1.1'."""
    for tag in tags:
        if tag.startswith("wcag") and len(tag) >= 7:
            digits = tag[4:]
            if digits.isdigit() and len(digits) >= 3:
                return f"{digits[0]}.{digits[1]}.{digits[2:]}"
    return ""


def scan(
    url: str,
    viewports: Optional[list[str]] = None,
    include_aria: bool = True,
) -> ScanResult:
    """Scan a URL for accessibility issues.

    Args:
        url: Full URL to scan (e.g. https://example.com)
        viewports: List of viewport names to test. Default: all.
        include_aria: Whether to capture the ARIA accessibility tree.
    """
    from playwright.sync_api import sync_playwright

    if viewports is None:
        viewports = list(VIEWPORTS.keys())

    start = datetime.now()
    result = ScanResult(
        url=url,
        timestamp=start.isoformat(),
        viewports_tested=viewports,
    )
    seen_issues: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for vp_name in viewports:
            config = VIEWPORTS.get(vp_name, VIEWPORTS["desktop"])
            context = browser.new_context(
                viewport={"width": config["width"], "height": config["height"]},
                is_mobile=config.get("is_mobile", False),
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(500)

                # 1. Run axe-core
                page.evaluate(AXE_JS)
                axe_results = page.evaluate("""() => {
                    return new Promise((resolve) => {
                        axe.run(document, {
                            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag22aa'] }
                        }).then(results => resolve(JSON.stringify(results)));
                    });
                }""")
                axe_data = json.loads(axe_results)

                for violation in axe_data.get("violations", []):
                    for node in violation.get("nodes", []):
                        dedup_key = f"{violation['id']}:{node.get('target', [''])[0] if node.get('target') else ''}:{vp_name}"
                        if dedup_key in seen_issues:
                            continue
                        seen_issues.add(dedup_key)

                        result.issues.append(Issue(
                            rule_id=violation["id"],
                            wcag=_extract_wcag(violation.get("tags", [])),
                            impact=violation.get("impact", "moderate"),
                            description=violation.get("help", violation.get("description", "")),
                            help_url=violation.get("helpUrl", ""),
                            element_html=node.get("html", ""),
                            selector=node.get("target", [""])[0] if node.get("target") else "",
                            viewport=vp_name,
                            source="axe-core",
                        ))

                # Store axe summary (first viewport only)
                if not result.axe_summary:
                    result.axe_summary = {
                        "violations": len(axe_data.get("violations", [])),
                        "passes": len(axe_data.get("passes", [])),
                        "incomplete": len(axe_data.get("incomplete", [])),
                        "inapplicable": len(axe_data.get("inapplicable", [])),
                    }

                # 2. Check for overflow:hidden clipping (TechAccess custom check)
                try:
                    clipped = page.evaluate(CLIPPING_CHECK_JS)
                    for clip in clipped:
                        dedup_key = f"overflow-clip:{clip['parent']}:{vp_name}"
                        if dedup_key not in seen_issues:
                            seen_issues.add(dedup_key)
                            result.issues.append(Issue(
                                rule_id="overflow-clip",
                                wcag="1.4.10",
                                impact="serious",
                                description=f"Content clipped by overflow:hidden — {clip['child']} overflows {clip['parent']} by {clip['clipped_px']}px",
                                element_html=clip.get("html", ""),
                                selector=clip["parent"],
                                viewport=vp_name,
                                source="techaccess",
                            ))
                except Exception:
                    pass

                # 3. Capture ARIA tree (first viewport only)
                if include_aria and not result.aria_tree:
                    try:
                        yaml_snap = page.locator(":root").aria_snapshot()
                        result.aria_tree = {"format": "yaml", "content": yaml_snap}
                    except Exception:
                        try:
                            client = page.context.new_cdp_session(page)
                            cdp_tree = client.send("Accessibility.getFullAXTree")
                            result.aria_tree = {
                                "format": "cdp",
                                "node_count": len(cdp_tree.get("nodes", [])),
                            }
                        except Exception:
                            result.aria_tree = {}

            except Exception as e:
                result.issues.append(Issue(
                    rule_id="scan-error",
                    wcag="",
                    impact="critical",
                    description=f"Scan failed on {vp_name}: {str(e)}",
                    viewport=vp_name,
                    source="scanner",
                ))
            finally:
                context.close()

        browser.close()

    elapsed = (datetime.now() - start).total_seconds()
    result.scan_time_ms = int(elapsed * 1000)
    return result


def snapshot(url: str) -> dict:
    """Capture the ARIA accessibility tree for a URL.

    Returns YAML representation via Playwright's aria_snapshot API,
    plus a CDP node count for completeness.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(500)

        result = {"url": url}
        try:
            result["aria_tree"] = page.locator(":root").aria_snapshot()
        except Exception:
            result["aria_tree"] = ""

        try:
            client = page.context.new_cdp_session(page)
            cdp_tree = client.send("Accessibility.getFullAXTree")
            result["cdp_node_count"] = len(cdp_tree.get("nodes", []))
        except Exception:
            result["cdp_node_count"] = 0

        browser.close()

    return result


def contrast_check(url: str) -> list[dict]:
    """Check color contrast ratios on a page.

    Returns list of elements with insufficient contrast and suggested fixes.
    """
    from playwright.sync_api import sync_playwright

    contrast_js = """() => {
        function srgb(c) { return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
        function lum(r, g, b) { return 0.2126 * srgb(r/255) + 0.7152 * srgb(g/255) + 0.0722 * srgb(b/255); }
        function parse(s) {
            const m = s.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            return m ? { r: +m[1], g: +m[2], b: +m[3] } : null;
        }
        function effBg(el) {
            let n = el, bg = { r: 255, g: 255, b: 255 };
            while (n && n !== document.documentElement) {
                const c = parse(getComputedStyle(n).backgroundColor);
                if (c) { bg = c; break; }
                n = n.parentElement;
            }
            return bg;
        }
        function ratio(fg, bg) {
            const l1 = lum(fg.r, fg.g, fg.b), l2 = lum(bg.r, bg.g, bg.b);
            return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        }

        const results = [];
        const els = Array.from(document.querySelectorAll('h1,h2,h3,h4,p,span,a,li,label,button,td,th'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && el.textContent.trim() && !el.children.length;
            }).slice(0, 50);

        els.forEach(el => {
            const cs = getComputedStyle(el);
            const fg = parse(cs.color);
            if (!fg) return;
            const bg = effBg(el);
            const r = ratio(fg, bg);
            const size = parseFloat(cs.fontSize);
            const bold = parseInt(cs.fontWeight) >= 700;
            const large = size >= 18 || (size >= 14 && bold);
            const min = large ? 3 : 4.5;
            results.push({
                text: el.textContent.trim().substring(0, 40),
                tag: el.tagName.toLowerCase(),
                fontSize: size,
                ratio: Math.round(r * 100) / 100,
                required: min,
                pass: r >= min,
                fg: `rgb(${fg.r},${fg.g},${fg.b})`,
                bg: `rgb(${bg.r},${bg.g},${bg.b})`,
                selector: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : ''),
            });
        });
        return results;
    }"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(500)
        results = page.evaluate(contrast_js)
        browser.close()

    return results
