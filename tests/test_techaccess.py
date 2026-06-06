"""TechAccess test suite."""

import json
import pytest

from techaccess.scanner import ScanResult, Issue, _extract_wcag, VIEWPORTS
from techaccess.score import calculate, Score, IMPACT_WEIGHTS
from techaccess.report import to_json, to_markdown, to_sarif


# --- Fixtures ---

def make_issue(rule_id="color-contrast", wcag="1.4.3", impact="serious", **kwargs):
    defaults = {
        "description": "Elements must meet minimum color contrast ratio thresholds",
        "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        "element_html": "<p style='color: #777'>Low contrast text</p>",
        "selector": "p.low-contrast",
        "viewport": "desktop",
        "source": "axe-core",
    }
    defaults.update(kwargs)
    return Issue(rule_id=rule_id, wcag=wcag, impact=impact, **defaults)


def make_result(issues=None, url="https://example.com"):
    return ScanResult(
        url=url,
        timestamp="2026-06-06T12:00:00",
        issues=issues or [],
        viewports_tested=["mobile", "desktop"],
        scan_time_ms=1234,
        axe_summary={"violations": 2, "passes": 50, "incomplete": 3, "inapplicable": 10},
    )


# --- Scanner tests ---

class TestExtractWcag:
    def test_standard_tag(self):
        assert _extract_wcag(["wcag2a", "wcag111", "cat.semantics"]) == "1.1.1"

    def test_three_digit(self):
        assert _extract_wcag(["wcag143"]) == "1.4.3"

    def test_four_digit(self):
        assert _extract_wcag(["wcag1410"]) == "1.4.10"

    def test_no_wcag(self):
        assert _extract_wcag(["cat.color", "best-practice"]) == ""

    def test_empty(self):
        assert _extract_wcag([]) == ""

    def test_short_tag(self):
        assert _extract_wcag(["wcag2a"]) == ""


class TestScanResult:
    def test_violation_count(self):
        result = make_result([make_issue(), make_issue(rule_id="image-alt")])
        assert result.violation_count == 2

    def test_critical_count(self):
        result = make_result([
            make_issue(impact="critical"),
            make_issue(impact="serious"),
            make_issue(impact="critical"),
        ])
        assert result.critical_count == 2

    def test_serious_count(self):
        result = make_result([make_issue(impact="serious")])
        assert result.serious_count == 1

    def test_empty_result(self):
        result = make_result()
        assert result.violation_count == 0
        assert result.critical_count == 0

    def test_issues_by_impact(self):
        result = make_result([
            make_issue(impact="critical"),
            make_issue(impact="serious"),
            make_issue(impact="critical", rule_id="image-alt"),
        ])
        by_impact = result.issues_by_impact()
        assert len(by_impact["critical"]) == 2
        assert len(by_impact["serious"]) == 1

    def test_to_dict(self):
        result = make_result([make_issue()])
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["summary"]["total"] == 1
        assert len(d["issues"]) == 1
        assert d["issues"][0]["rule_id"] == "color-contrast"


class TestPreTable:
    def test_pre_table_issue(self):
        issue = make_issue(
            rule_id="pre-table",
            wcag="1.3.1",
            impact="moderate",
            description="ASCII table in <pre> block (box-drawing, 12 lines) — wraps poorly on mobile. Convert to HTML <table>.",
            source="techaccess",
        )
        assert issue.rule_id == "pre-table"
        assert issue.wcag == "1.3.1"
        assert issue.source == "techaccess"

    def test_pre_table_score(self):
        issues = [make_issue(rule_id="pre-table", impact="moderate", source="techaccess")]
        score = calculate(issues)
        assert score.value == 95  # -5 for moderate

    def test_pre_table_in_report(self):
        result = make_result([
            make_issue(rule_id="pre-table", impact="moderate",
                       description="ASCII table in pre block", source="techaccess"),
        ])
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert "pre-table" in md
        assert "Moderate" in md


class TestOverflowClip:
    def test_clip_issue_structure(self):
        issue = make_issue(
            rule_id="overflow-clip",
            wcag="1.4.10",
            impact="serious",
            description="Content clipped by overflow:hidden — div.grid overflows div.lesson-visual by 120px",
            source="techaccess",
        )
        assert issue.rule_id == "overflow-clip"
        assert issue.source == "techaccess"
        assert issue.wcag == "1.4.10"

    def test_clip_in_score(self):
        issues = [make_issue(rule_id="overflow-clip", impact="serious", source="techaccess")]
        score = calculate(issues)
        assert score.value == 90  # -10 for serious

    def test_clip_in_report(self):
        result = make_result([
            make_issue(rule_id="overflow-clip", impact="serious",
                       description="Content clipped by overflow:hidden", source="techaccess"),
        ])
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert "overflow-clip" in md
        assert "Serious" in md


class TestViewports:
    def test_mobile_exists(self):
        assert "mobile" in VIEWPORTS

    def test_desktop_exists(self):
        assert "desktop" in VIEWPORTS

    def test_tablet_exists(self):
        assert "tablet" in VIEWPORTS

    def test_mobile_is_mobile(self):
        assert VIEWPORTS["mobile"]["is_mobile"] is True

    def test_desktop_not_mobile(self):
        assert VIEWPORTS["desktop"]["is_mobile"] is False


# --- Score tests ---

class TestScore:
    def test_perfect_score(self):
        score = calculate([])
        assert score.value == 100
        assert score.grade == "A+"

    def test_single_critical(self):
        score = calculate([make_issue(impact="critical")])
        assert score.value == 100 - IMPACT_WEIGHTS["critical"]
        assert score.grade != "A+"

    def test_dedup_same_rule(self):
        """Same rule on mobile and desktop should count once for scoring."""
        issues = [
            make_issue(viewport="mobile"),
            make_issue(viewport="desktop"),
        ]
        score = calculate(issues)
        assert score.value == 100 - IMPACT_WEIGHTS["serious"]
        assert score.total_issues == 2  # Total reported, but deduped for scoring

    def test_multiple_rules(self):
        issues = [
            make_issue(rule_id="color-contrast", impact="serious"),
            make_issue(rule_id="image-alt", impact="critical"),
            make_issue(rule_id="label", impact="moderate"),
        ]
        score = calculate(issues)
        expected = 100 - IMPACT_WEIGHTS["serious"] - IMPACT_WEIGHTS["critical"] - IMPACT_WEIGHTS["moderate"]
        assert score.value == expected

    def test_floor_at_zero(self):
        issues = [make_issue(rule_id=f"rule-{i}", impact="critical") for i in range(20)]
        score = calculate(issues)
        assert score.value == 0
        assert score.grade == "F"

    def test_grade_boundaries(self):
        # 100 = A+
        assert calculate([]).grade == "A+"
        # 85-89 = A-
        issues = [make_issue(rule_id="r1", impact="critical")]  # -15 = 85
        assert calculate(issues).grade == "A-"

    def test_impact_counts(self):
        issues = [
            make_issue(impact="critical"),
            make_issue(impact="critical", rule_id="r2"),
            make_issue(impact="serious", rule_id="r3"),
            make_issue(impact="minor", rule_id="r4"),
        ]
        score = calculate(issues)
        assert score.critical == 2
        assert score.serious == 1
        assert score.minor == 1

    def test_to_dict(self):
        score = calculate([make_issue()])
        d = score.to_dict()
        assert "score" in d
        assert "grade" in d
        assert "by_impact" in d

    def test_highest_impact_wins(self):
        """Same rule with different impacts across viewports — highest should win."""
        issues = [
            make_issue(rule_id="r1", impact="minor", viewport="mobile"),
            make_issue(rule_id="r1", impact="critical", viewport="desktop"),
        ]
        score = calculate(issues)
        assert score.value == 100 - IMPACT_WEIGHTS["critical"]


# --- Report tests ---

class TestJsonReport:
    def test_valid_json(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        output = to_json(result, score)
        parsed = json.loads(output)
        assert parsed["tool"] == "techaccess"
        assert parsed["url"] == "https://example.com"

    def test_includes_score(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        parsed = json.loads(to_json(result, score))
        assert "score" in parsed["score"]
        assert "grade" in parsed["score"]

    def test_includes_issues(self):
        result = make_result([make_issue(), make_issue(rule_id="image-alt")])
        score = calculate(result.issues)
        parsed = json.loads(to_json(result, score))
        assert len(parsed["issues"]) == 2

    def test_empty_result(self):
        result = make_result()
        score = calculate(result.issues)
        parsed = json.loads(to_json(result, score))
        assert parsed["score"]["score"] == 100


class TestMarkdownReport:
    def test_contains_grade(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert score.grade in md

    def test_contains_url(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert "https://example.com" in md

    def test_perfect_score_message(self):
        result = make_result()
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert "No accessibility issues found" in md

    def test_issue_sections(self):
        result = make_result([
            make_issue(impact="critical", rule_id="r1"),
            make_issue(impact="serious", rule_id="r2"),
        ])
        score = calculate(result.issues)
        md = to_markdown(result, score)
        assert "Critical Issues" in md
        assert "Serious Issues" in md

    def test_generated_by(self):
        result = make_result()
        score = calculate([])
        md = to_markdown(result, score)
        assert "TechAccess" in md


class TestSarifReport:
    def test_valid_sarif(self):
        result = make_result([make_issue()])
        output = to_sarif(result)
        parsed = json.loads(output)
        assert parsed["version"] == "2.1.0"
        assert parsed["runs"][0]["tool"]["driver"]["name"] == "TechAccess"

    def test_rules_deduped(self):
        result = make_result([
            make_issue(viewport="mobile"),
            make_issue(viewport="desktop"),
        ])
        parsed = json.loads(to_sarif(result))
        rules = parsed["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1  # Same rule deduped

    def test_results_not_deduped(self):
        result = make_result([
            make_issue(viewport="mobile"),
            make_issue(viewport="desktop"),
        ])
        parsed = json.loads(to_sarif(result))
        results = parsed["runs"][0]["results"]
        assert len(results) == 2  # Each instance reported

    def test_impact_mapping(self):
        result = make_result([make_issue(impact="critical")])
        parsed = json.loads(to_sarif(result))
        assert parsed["runs"][0]["results"][0]["level"] == "error"
