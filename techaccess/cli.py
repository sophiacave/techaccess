"""TechAccess CLI — Command-line accessibility auditing.

Usage:
    techaccess audit https://example.com
    techaccess audit https://example.com --ai          # with AI analysis
    techaccess fix https://example.com                 # AI-generated fixes
    techaccess evaluate https://example.com            # evaluate alt text
    techaccess snapshot https://example.com
    techaccess contrast https://example.com
"""

import json
import os
import sys

import click

from . import __version__
from .scanner import scan, snapshot, contrast_check
from .score import calculate
from .report import to_json, to_markdown, to_sarif, to_html


@click.group()
@click.version_option(version=__version__)
def main():
    """TechAccess -- AI-powered accessibility toolkit."""
    pass


@main.command()
@click.argument("url")
@click.option("--viewports", "-v", default=None, help="Comma-separated viewports: mobile,tablet,desktop")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown", "sarif", "html"]), default="markdown")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--ai", is_flag=True, help="Enable AI semantic analysis (requires Ollama or --claude-key)")
@click.option("--claude-key", envvar="CLAUDE_API_KEY", default=None, help="Claude API key for cloud AI")
@click.option("--fail-on", type=click.Choice(["critical", "serious", "moderate", "minor"]), default=None,
              help="Exit with code 1 if issues at this level or above exist (CI mode)")
def audit(url: str, viewports: str | None, fmt: str, output: str | None,
          ai: bool, claude_key: str | None, fail_on: str | None):
    """Run a full accessibility audit on a URL."""
    vp_list = viewports.split(",") if viewports else None

    click.echo(f"Scanning {url}...", err=True)
    result = scan(url, viewports=vp_list)

    if ai:
        click.echo("Running AI semantic analysis...", err=True)
        from .analyzer import analyze_aria
        ai_issues = analyze_aria(result, claude_api_key=claude_key)
        if ai_issues:
            result.issues.extend(ai_issues)
            click.echo(f"  AI found {len(ai_issues)} additional issues", err=True)

    score = calculate(result.issues)

    if fmt == "json":
        content = to_json(result, score)
    elif fmt == "sarif":
        content = to_sarif(result)
    elif fmt == "html":
        content = to_html(result, score)
    else:
        content = to_markdown(result, score)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(content)

    if fail_on:
        impact_order = {"critical": 4, "serious": 3, "moderate": 2, "minor": 1}
        threshold = impact_order.get(fail_on, 0)
        for issue in result.issues:
            if impact_order.get(issue.impact, 0) >= threshold:
                sys.exit(1)


@main.command()
@click.argument("url")
@click.option("--viewports", "-v", default=None, help="Comma-separated viewports")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown"]), default="markdown")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--claude-key", envvar="CLAUDE_API_KEY", default=None, help="Claude API key")
def fix(url: str, viewports: str | None, fmt: str, output: str | None, claude_key: str | None):
    """Generate AI-powered code fixes for accessibility issues."""
    from .analyzer import analyze_aria
    from .remediator import generate_fixes, fixes_to_markdown, fixes_to_json

    vp_list = viewports.split(",") if viewports else None

    click.echo(f"Scanning {url}...", err=True)
    result = scan(url, viewports=vp_list)

    click.echo(f"Generating fixes for {len(result.issues)} issues...", err=True)
    aria_content = result.aria_tree.get("content", "") if result.aria_tree else ""
    fixes = generate_fixes(
        result.issues, aria_tree=aria_content, url=url, claude_api_key=claude_key
    )

    if fmt == "json":
        content = fixes_to_json(fixes)
    else:
        content = fixes_to_markdown(fixes)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Fixes written to {output}", err=True)
    else:
        click.echo(content)


@main.command()
@click.argument("url")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--claude-key", envvar="CLAUDE_API_KEY", default=None, help="Claude API key")
def evaluate(url: str, output: str | None, claude_key: str | None):
    """Evaluate quality of existing alt text on a page."""
    from .analyzer import extract_images, evaluate_alt_text
    from .scanner import snapshot

    click.echo(f"Extracting images from {url}...", err=True)
    images = extract_images(url)

    if not images:
        click.echo("No visible images found on page.")
        return

    click.echo(f"Found {len(images)} images. Evaluating alt text...", err=True)

    tree = snapshot(url)
    aria_excerpt = tree.get("aria_tree", "")

    evaluations = evaluate_alt_text(
        url, images, aria_excerpt=aria_excerpt, claude_api_key=claude_key
    )

    if not evaluations:
        click.echo("Could not evaluate alt text (AI model unavailable).", err=True)
        return

    if output:
        content = json.dumps([e.to_dict() for e in evaluations], indent=2)
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Evaluation written to {output}", err=True)
    else:
        avg_score = sum(e.score for e in evaluations) / len(evaluations)
        click.echo(f"\nAlt Text Quality: {avg_score:.1f}/5.0 average ({len(evaluations)} images)\n")
        for e in evaluations:
            stars = "*" * e.score + "." * (5 - e.score)
            src_short = e.src.split("/")[-1][:40] if e.src else "unknown"
            color = "green" if e.score >= 4 else "yellow" if e.score >= 3 else "red"
            click.echo(click.style(f"  [{stars}] {src_short}", fg=color))
            click.echo(f"    alt: \"{e.current_alt[:60]}\"")
            if e.suggested_alt:
                click.echo(click.style(f"    fix: \"{e.suggested_alt[:60]}\"", fg="cyan"))
            if e.issues:
                for issue in e.issues[:2]:
                    click.echo(f"    - {issue}")
            click.echo()


@main.command()
@click.argument("url")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--claude-key", envvar="CLAUDE_API_KEY", default=None, help="Claude API key")
def alttext(url: str, output: str | None, claude_key: str | None):
    """Generate alt text for images missing or with poor alt text."""
    from .analyzer import generate_alt_text, extract_images
    from .scanner import snapshot

    click.echo(f"Extracting images from {url}...", err=True)
    images = extract_images(url)

    if not images:
        click.echo("No visible images found on page.")
        return

    click.echo(f"Found {len(images)} images. Generating alt text...", err=True)

    tree = snapshot(url)
    aria_excerpt = tree.get("aria_tree", "")

    results = generate_alt_text(
        url, images=images, aria_excerpt=aria_excerpt, claude_api_key=claude_key
    )

    if not results:
        click.echo("No images need alt text (all have adequate descriptions).")
        return

    if output:
        content = json.dumps(results, indent=2)
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Alt text written to {output}", err=True)
    else:
        click.echo(f"\nGenerated alt text for {len(results)} images:\n")
        for r in results:
            src_short = r["src"].split("/")[-1][:40] if r["src"] else "unknown"
            if r.get("decorative"):
                click.echo(click.style(f"  [DECORATIVE] {src_short}", fg="yellow"))
                click.echo(f"    alt: \"\" (mark as decorative)")
            else:
                conf = r.get("confidence", 0)
                color = "green" if conf >= 0.7 else "yellow"
                click.echo(click.style(f"  [{r.get('model', 'ai')}] {src_short}", fg=color))
                click.echo(f"    alt: \"{r['alt'][:80]}\"")
            click.echo()


@main.command()
@click.argument("url")
@click.option("--output", "-o", default=None, help="Output file path")
def snapshot_cmd(url: str, output: str | None):
    """Capture the ARIA accessibility tree for a URL."""
    click.echo(f"Capturing ARIA tree for {url}...", err=True)
    tree = snapshot(url)
    content = json.dumps(tree, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"ARIA tree written to {output}", err=True)
    else:
        click.echo(content)


snapshot_cmd.name = "snapshot"


@main.command()
@click.argument("url")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--failures-only", is_flag=True, help="Only show elements that fail contrast checks")
def contrast(url: str, output: str | None, failures_only: bool):
    """Check color contrast ratios against WCAG requirements."""
    click.echo(f"Checking contrast for {url}...", err=True)
    results = contrast_check(url)

    if failures_only:
        results = [r for r in results if not r["pass"]]

    content = json.dumps(results, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Contrast report written to {output}", err=True)
    else:
        passed = sum(1 for r in results if r["pass"])
        failed = sum(1 for r in results if not r["pass"])
        total = len(results)

        click.echo(f"\nContrast Results: {passed}/{total} pass, {failed}/{total} fail\n")
        for r in results:
            status = "PASS" if r["pass"] else "FAIL"
            color = "green" if r["pass"] else "red"
            click.echo(click.style(
                f"  [{status}] {r['ratio']}:1 (need {r['required']}:1) -- "
                f"{r['tag']} \"{r['text'][:30]}\" -- fg:{r['fg']} bg:{r['bg']}",
                fg=color,
            ))


@main.command()
@click.argument("url")
@click.option("--max-pages", "-n", default=20, help="Maximum pages to scan (default: 20)")
@click.option("--viewports", "-v", default=None, help="Comma-separated viewports (default: desktop only for speed)")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown"]), default="markdown")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--fail-on", type=click.Choice(["critical", "serious", "moderate", "minor"]), default=None,
              help="Exit with code 1 if issues at this level or above exist (CI mode)")
def crawl(url: str, max_pages: int, viewports: str | None, fmt: str, output: str | None, fail_on: str | None):
    """Crawl multiple pages and audit each for accessibility issues."""
    from .crawler import crawl as do_crawl

    vp_list = viewports.split(",") if viewports else None

    click.echo(f"Discovering pages from {url}...", err=True)
    result = do_crawl(url, max_pages=max_pages, viewports=vp_list)
    click.echo(f"Scanned {len(result.pages)} pages in {result.total_scan_time_ms}ms", err=True)

    if fmt == "json":
        content = json.dumps(result.to_dict(), indent=2)
    else:
        from .score import calculate
        lines = [
            f"# TechAccess Site Crawl Report",
            f"",
            f"**Base URL:** {result.base_url}",
            f"**Pages scanned:** {len(result.pages)}",
            f"**Average score:** {result.avg_score:.0f}/100",
            f"**Total issues:** {result.total_issues}",
            f"**Scan time:** {result.total_scan_time_ms}ms",
            f"",
            f"## Pages",
            f"",
            f"| Page | Score | Grade | Issues |",
            f"|------|-------|-------|--------|",
        ]
        for page in result.pages:
            s = calculate(page.issues)
            short_url = page.url.replace(result.base_url, "") or "/"
            lines.append(f"| {short_url} | {s.value}/100 | {s.grade} | {page.violation_count} |")

        if result.total_issues > 0:
            lines.extend(["", "## Issues by Page", ""])
            for page in result.pages:
                if page.violation_count > 0:
                    short_url = page.url.replace(result.base_url, "") or "/"
                    lines.append(f"### {short_url} ({page.violation_count} issues)")
                    for issue in page.issues:
                        lines.append(f"- **{issue.rule_id}** ({issue.impact}) — {issue.description}")
                    lines.append("")

        lines.append(f"---")
        lines.append(f"*Generated by [TechAccess](https://github.com/sophiacave/techaccess) v{__version__}*")
        content = "\n".join(lines)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(content)

    if fail_on:
        impact_order = {"critical": 4, "serious": 3, "moderate": 2, "minor": 1}
        threshold = impact_order.get(fail_on, 0)
        for page in result.pages:
            for issue in page.issues:
                if impact_order.get(issue.impact, 0) >= threshold:
                    sys.exit(1)


if __name__ == "__main__":
    main()
