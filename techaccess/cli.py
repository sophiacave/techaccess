"""TechAccess CLI — Command-line accessibility auditing.

Usage:
    techaccess audit https://example.com
    techaccess snapshot https://example.com
    techaccess contrast https://example.com
    techaccess report https://example.com --format html
"""

import json
import sys

import click

from . import __version__
from .scanner import scan, snapshot, contrast_check
from .score import calculate
from .report import to_json, to_markdown, to_sarif


@click.group()
@click.version_option(version=__version__)
def main():
    """TechAccess — AI-powered accessibility toolkit."""
    pass


@main.command()
@click.argument("url")
@click.option("--viewports", "-v", default=None, help="Comma-separated viewports: mobile,tablet,desktop")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown", "sarif"]), default="markdown")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--fail-on", type=click.Choice(["critical", "serious", "moderate", "minor"]), default=None,
              help="Exit with code 1 if issues at this level or above exist (CI mode)")
def audit(url: str, viewports: str | None, fmt: str, output: str | None, fail_on: str | None):
    """Run a full accessibility audit on a URL."""
    vp_list = viewports.split(",") if viewports else None

    click.echo(f"Scanning {url}...", err=True)
    result = scan(url, viewports=vp_list)
    score = calculate(result.issues)

    if fmt == "json":
        content = to_json(result, score)
    elif fmt == "sarif":
        content = to_sarif(result)
    else:
        content = to_markdown(result, score)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(content)

    # CI mode: exit with code 1 if issues meet threshold
    if fail_on:
        impact_order = {"critical": 4, "serious": 3, "moderate": 2, "minor": 1}
        threshold = impact_order.get(fail_on, 0)
        for issue in result.issues:
            if impact_order.get(issue.impact, 0) >= threshold:
                sys.exit(1)


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


# Register with correct name
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
        # Pretty print for terminal
        passed = sum(1 for r in results if r["pass"])
        failed = sum(1 for r in results if not r["pass"])
        total = len(results)

        click.echo(f"\nContrast Results: {passed}/{total} pass, {failed}/{total} fail\n")
        for r in results:
            status = "PASS" if r["pass"] else "FAIL"
            color = "green" if r["pass"] else "red"
            click.echo(click.style(
                f"  [{status}] {r['ratio']}:1 (need {r['required']}:1) — "
                f"{r['tag']} \"{r['text'][:30]}\" — fg:{r['fg']} bg:{r['bg']}",
                fg=color,
            ))


if __name__ == "__main__":
    main()
