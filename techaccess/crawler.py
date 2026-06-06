"""TechAccess Crawler — Multi-page accessibility scanning.

Discovers pages via sitemap.xml or link extraction, then scans each page.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .scanner import Issue, ScanResult, VIEWPORTS, AXE_JS, _extract_wcag


@dataclass
class CrawlResult:
    """Aggregated results from scanning multiple pages."""
    base_url: str
    timestamp: str
    pages: list[ScanResult] = field(default_factory=list)
    total_scan_time_ms: int = 0

    @property
    def total_issues(self) -> int:
        return sum(r.violation_count for r in self.pages)

    @property
    def total_critical(self) -> int:
        return sum(r.critical_count for r in self.pages)

    @property
    def total_serious(self) -> int:
        return sum(r.serious_count for r in self.pages)

    @property
    def avg_score(self) -> float:
        if not self.pages:
            return 0.0
        from .score import calculate
        scores = [calculate(r.issues).value for r in self.pages]
        return sum(scores) / len(scores)

    @property
    def worst_pages(self) -> list[ScanResult]:
        from .score import calculate
        return sorted(self.pages, key=lambda r: calculate(r.issues).value)[:5]

    def to_dict(self) -> dict:
        from .score import calculate
        return {
            "base_url": self.base_url,
            "timestamp": self.timestamp,
            "pages_scanned": len(self.pages),
            "total_scan_time_ms": self.total_scan_time_ms,
            "summary": {
                "avg_score": round(self.avg_score, 1),
                "total_issues": self.total_issues,
                "critical": self.total_critical,
                "serious": self.total_serious,
                "pages_with_issues": sum(1 for r in self.pages if r.violation_count > 0),
                "perfect_pages": sum(1 for r in self.pages if r.violation_count == 0),
            },
            "pages": [
                {
                    "url": r.url,
                    "score": calculate(r.issues).value,
                    "grade": calculate(r.issues).grade,
                    "issues": r.violation_count,
                }
                for r in self.pages
            ],
        }


def discover_urls(base_url: str, max_pages: int = 20) -> list[str]:
    """Discover URLs from sitemap.xml or by crawling links."""
    urls = []

    # Try sitemap.xml first
    parsed = urlparse(base_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        resp = httpx.get(sitemap_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200 and "<urlset" in resp.text:
            root = ET.fromstring(resp.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//sm:loc", ns):
                if loc.text:
                    urls.append(loc.text)
            if urls:
                return urls[:max_pages]
    except Exception:
        pass

    # Fallback: extract links from the page
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(base_url, wait_until="networkidle", timeout=15000)
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href).filter(h => h.startsWith('http'))"
            )
            seen = {base_url}
            for link in links:
                link_parsed = urlparse(link)
                if link_parsed.netloc == parsed.netloc and link not in seen:
                    seen.add(link)
                    urls.append(link)
                    if len(urls) >= max_pages - 1:
                        break
        finally:
            browser.close()

    return [base_url] + urls[:max_pages - 1]


def crawl(
    base_url: str,
    max_pages: int = 20,
    viewports: Optional[list[str]] = None,
) -> CrawlResult:
    """Crawl multiple pages and scan each for accessibility issues.

    Args:
        base_url: Starting URL (sitemap.xml will be checked at the domain root).
        max_pages: Maximum number of pages to scan.
        viewports: Viewport names to test. Default: desktop only (for speed).
    """
    from playwright.sync_api import sync_playwright

    if viewports is None:
        viewports = ["desktop"]

    urls = discover_urls(base_url, max_pages)
    start = datetime.now()

    result = CrawlResult(
        base_url=base_url,
        timestamp=start.isoformat(),
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for url in urls:
            page_result = ScanResult(
                url=url,
                timestamp=datetime.now().isoformat(),
                viewports_tested=viewports,
            )
            seen_issues: set[str] = set()
            page_start = datetime.now()

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

                    # Run axe-core
                    page.evaluate(AXE_JS)
                    axe_result = page.evaluate("axe.run()")

                    if vp_name == viewports[0]:
                        page_result.axe_summary = {
                            "violations": len(axe_result.get("violations", [])),
                            "passes": len(axe_result.get("passes", [])),
                            "incomplete": len(axe_result.get("incomplete", [])),
                            "inapplicable": len(axe_result.get("inapplicable", [])),
                        }

                    for violation in axe_result.get("violations", []):
                        for node in violation.get("nodes", []):
                            dedup_key = f"{violation['id']}|{node.get('target', [''])[0] if node.get('target') else ''}"
                            if dedup_key in seen_issues:
                                continue
                            seen_issues.add(dedup_key)

                            page_result.issues.append(Issue(
                                rule_id=violation["id"],
                                wcag=_extract_wcag(violation.get("tags", [])),
                                impact=violation.get("impact", "minor"),
                                description=violation.get("description", ""),
                                help_url=violation.get("helpUrl", ""),
                                element_html=node.get("html", ""),
                                selector=", ".join(node.get("target", [])),
                                viewport=vp_name,
                            ))

                except Exception:
                    pass
                finally:
                    context.close()

            page_result.scan_time_ms = int((datetime.now() - page_start).total_seconds() * 1000)
            result.pages.append(page_result)

        browser.close()

    result.total_scan_time_ms = int((datetime.now() - start).total_seconds() * 1000)
    return result
