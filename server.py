"""TechAccess MCP Server — Accessibility tools for AI agents.

Install: claude mcp add techaccess -- python /path/to/server.py
"""

import json

from mcp.server.fastmcp import FastMCP

from techaccess.scanner import scan, snapshot, contrast_check
from techaccess.score import calculate
from techaccess.report import to_json, to_markdown

mcp = FastMCP("techaccess")


@mcp.tool()
def access_audit(
    url: str,
    viewports: str = "mobile,desktop",
    format: str = "markdown",
) -> str:
    """Run a full WCAG accessibility audit on any URL.

    Uses axe-core (industry standard) + ARIA tree analysis across viewports.
    Returns a score (0-100), letter grade, and detailed issues.

    Args:
        url: Full URL to audit (e.g. https://example.com)
        viewports: Comma-separated list: mobile, tablet, desktop
        format: Output format — markdown or json
    """
    vp_list = [v.strip() for v in viewports.split(",")]
    result = scan(url, viewports=vp_list)
    score = calculate(result.issues)

    if format == "json":
        return to_json(result, score)
    return to_markdown(result, score)


@mcp.tool()
def access_snapshot(url: str) -> str:
    """Capture the ARIA accessibility tree for a URL.

    Returns the full semantic structure as JSON — roles, names, properties.
    Useful for understanding how assistive technologies perceive a page.

    Args:
        url: Full URL to capture (e.g. https://example.com)
    """
    tree = snapshot(url)
    return json.dumps(tree, indent=2)


@mcp.tool()
def access_contrast(url: str, failures_only: bool = True) -> str:
    """Check color contrast ratios against WCAG requirements.

    Samples text elements and reports contrast ratios vs WCAG minimums.
    Returns pass/fail status with foreground and background colors.

    Args:
        url: Full URL to check
        failures_only: If true, only return elements that fail (default: true)
    """
    results = contrast_check(url)
    if failures_only:
        results = [r for r in results if not r["pass"]]

    if not results:
        return "All sampled text elements pass WCAG contrast requirements."

    return json.dumps(results, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
