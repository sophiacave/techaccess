"""TechAccess MCP Server — Accessibility tools for AI agents.

Install: claude mcp add techaccess -- python /path/to/server.py
"""

import json
import os

from mcp.server.fastmcp import FastMCP

from techaccess.scanner import scan, snapshot, contrast_check
from techaccess.score import calculate
from techaccess.report import to_json, to_markdown

mcp = FastMCP("techaccess")

CLAUDE_KEY = os.environ.get("CLAUDE_API_KEY")


@mcp.tool()
def access_audit(
    url: str,
    viewports: str = "mobile,desktop",
    format: str = "markdown",
    ai: bool = False,
) -> str:
    """Run a full WCAG accessibility audit on any URL.

    Uses axe-core (industry standard) + ARIA tree analysis across viewports.
    Returns a score (0-100), letter grade, and detailed issues.
    Set ai=True for AI semantic analysis that catches issues rules miss.

    Args:
        url: Full URL to audit (e.g. https://example.com)
        viewports: Comma-separated list: mobile, tablet, desktop
        format: Output format -- markdown or json
        ai: Enable AI semantic analysis (requires Ollama or CLAUDE_API_KEY)
    """
    vp_list = [v.strip() for v in viewports.split(",")]
    result = scan(url, viewports=vp_list)

    if ai:
        from techaccess.analyzer import analyze_aria
        ai_issues = analyze_aria(result, claude_api_key=CLAUDE_KEY)
        result.issues.extend(ai_issues)

    score = calculate(result.issues)

    if format == "json":
        return to_json(result, score)
    return to_markdown(result, score)


@mcp.tool()
def access_fix(
    url: str,
    viewports: str = "mobile,desktop",
    format: str = "markdown",
) -> str:
    """Generate AI-powered code fixes for accessibility issues.

    Scans the URL, analyzes issues with AI, then generates before/after
    HTML/ARIA code fixes for each issue.

    Args:
        url: Full URL to fix
        viewports: Comma-separated viewports
        format: Output format -- markdown or json
    """
    from techaccess.analyzer import analyze_aria
    from techaccess.remediator import generate_fixes, fixes_to_markdown, fixes_to_json

    vp_list = [v.strip() for v in viewports.split(",")]
    result = scan(url, viewports=vp_list)

    ai_issues = analyze_aria(result, claude_api_key=CLAUDE_KEY)
    result.issues.extend(ai_issues)

    aria_content = result.aria_tree.get("content", "") if result.aria_tree else ""
    fixes = generate_fixes(
        result.issues, aria_tree=aria_content, url=url, claude_api_key=CLAUDE_KEY
    )

    if format == "json":
        return fixes_to_json(fixes)
    return fixes_to_markdown(fixes)


@mcp.tool()
def access_alttext(url: str) -> str:
    """Generate alt text for images missing or with poor descriptions.

    Uses AI vision (llava locally, Claude Vision if API key set) to analyze
    each image and generate context-aware alt text. Only processes images
    that are missing alt text or have generic descriptions.

    Args:
        url: Full URL to process
    """
    from techaccess.analyzer import generate_alt_text

    results = generate_alt_text(url, claude_api_key=CLAUDE_KEY)

    if not results:
        return "All images have adequate alt text. No generation needed."

    return json.dumps(results, indent=2)


@mcp.tool()
def access_evaluate_alt(url: str) -> str:
    """Evaluate quality of existing alt text on a page.

    Extracts all visible images, evaluates their alt text for quality
    using AI, and suggests improvements. Scores each image 1-5.

    Args:
        url: Full URL to evaluate
    """
    from techaccess.analyzer import extract_images, evaluate_alt_text

    images = extract_images(url)
    if not images:
        return "No visible images found on page."

    tree = snapshot(url)
    aria_excerpt = tree.get("aria_tree", "")

    evaluations = evaluate_alt_text(
        url, images, aria_excerpt=aria_excerpt, claude_api_key=CLAUDE_KEY
    )

    if not evaluations:
        return "Could not evaluate alt text (no AI model available)."

    return json.dumps([e.to_dict() for e in evaluations], indent=2)


@mcp.tool()
def access_snapshot(url: str) -> str:
    """Capture the ARIA accessibility tree for a URL.

    Returns the full semantic structure as JSON -- roles, names, properties.
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
