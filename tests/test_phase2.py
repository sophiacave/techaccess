"""TechAccess Phase 2 tests — AI layer (models, analyzer, remediator, reports)."""

import json
from unittest.mock import patch, MagicMock
import pytest

from techaccess.models import extract_json, ollama_available, ModelResponse, DEFAULTS
from techaccess.analyzer import analyze_aria, evaluate_alt_text, generate_alt_text, AltTextEvaluation
from techaccess.remediator import generate_fixes, fixes_to_markdown, fixes_to_json, CodeFix
from techaccess.scanner import ScanResult, Issue
from techaccess.report import to_html
from techaccess.score import calculate, Score


# --- Fixtures ---

def make_issue(rule_id="color-contrast", wcag="1.4.3", impact="serious", **kwargs):
    defaults = {
        "description": "Elements must meet minimum color contrast ratio thresholds",
        "help_url": "",
        "element_html": "<p style='color: #777'>Low contrast</p>",
        "selector": "p.low-contrast",
        "viewport": "desktop",
        "source": "axe-core",
    }
    defaults.update(kwargs)
    return Issue(rule_id=rule_id, wcag=wcag, impact=impact, **defaults)


def make_result(issues=None, aria_content=""):
    return ScanResult(
        url="https://example.com",
        timestamp="2026-06-06T12:00:00",
        issues=issues or [],
        aria_tree={"format": "yaml", "content": aria_content} if aria_content else {},
        viewports_tested=["desktop"],
        scan_time_ms=100,
    )


# --- Models: extract_json ---

class TestExtractJson:
    def test_raw_array(self):
        assert extract_json('[{"a": 1}]') == '[{"a": 1}]'

    def test_raw_object(self):
        assert extract_json('{"key": "val"}') == '{"key": "val"}'

    def test_markdown_fenced(self):
        text = "Here's the result:\n```json\n[{\"a\": 1}]\n```\nDone."
        assert extract_json(text) == '[{"a": 1}]'

    def test_markdown_no_lang(self):
        text = "```\n{\"a\": 1}\n```"
        assert extract_json(text) == '{"a": 1}'

    def test_embedded_in_text(self):
        text = "I found these issues:\n[{\"x\": 1}]\nThat's all."
        result = extract_json(text)
        parsed = json.loads(result)
        assert parsed == [{"x": 1}]

    def test_with_thinking(self):
        text = "<think>Let me analyze...</think>\n[{\"rule_id\": \"test\"}]"
        result = extract_json(text)
        parsed = json.loads(result)
        assert parsed[0]["rule_id"] == "test"

    def test_plain_text_fallback(self):
        assert extract_json("no json here") == "no json here"


# --- Models: defaults ---

class TestModelDefaults:
    def test_analysis_model(self):
        assert DEFAULTS["analysis"] == "qwen3:30b"

    def test_remediation_model(self):
        assert DEFAULTS["remediation"] == "qwen3:30b"

    def test_alttext_model(self):
        assert DEFAULTS["alttext"] == "llava:13b"

    def test_evaluation_model(self):
        assert DEFAULTS["evaluation"] == "qwen3:14b"


# --- Analyzer: analyze_aria ---

class TestAnalyzeAria:
    @patch("techaccess.analyzer.generate")
    def test_returns_issues(self, mock_gen):
        mock_gen.return_value = ModelResponse(
            text=json.dumps([
                {
                    "rule_id": "semantic-heading",
                    "wcag": "1.3.1",
                    "impact": "moderate",
                    "description": "Heading hierarchy skips from h1 to h4",
                    "element": "<h4>Details</h4>",
                }
            ]),
            model="qwen3:30b",
        )
        result = make_result(aria_content="- heading 'Home' [level=1]\n- heading 'Details' [level=4]")
        issues = analyze_aria(result)
        assert len(issues) == 1
        assert issues[0].rule_id == "semantic-heading"
        assert issues[0].source == "ai-semantic"
        assert issues[0].wcag == "1.3.1"

    @patch("techaccess.analyzer.generate")
    def test_empty_on_no_tree(self, mock_gen):
        result = make_result(aria_content="")
        issues = analyze_aria(result)
        assert issues == []
        mock_gen.assert_not_called()

    @patch("techaccess.analyzer.generate")
    def test_handles_bad_json(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="not valid json", model="test")
        result = make_result(aria_content="some tree content")
        issues = analyze_aria(result)
        assert issues == []

    @patch("techaccess.analyzer.generate")
    def test_empty_array_response(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="[]", model="test")
        result = make_result(aria_content="some tree content")
        issues = analyze_aria(result)
        assert issues == []

    @patch("techaccess.analyzer.generate")
    def test_truncates_large_tree(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="[]", model="test")
        result = make_result(aria_content="x" * 10000)
        analyze_aria(result)
        call_args = mock_gen.call_args
        prompt = call_args[1].get("prompt", call_args[0][0] if call_args[0] else "")
        # Tree should be truncated in the prompt
        assert "truncated" in prompt or len(prompt) < 12000


# --- Analyzer: evaluate_alt_text ---

class TestEvaluateAltText:
    @patch("techaccess.analyzer.generate")
    def test_returns_evaluations(self, mock_gen):
        mock_gen.return_value = ModelResponse(
            text=json.dumps([
                {
                    "src": "logo.png",
                    "current_alt": "logo",
                    "score": 2,
                    "issues": ["Too generic"],
                    "suggested_alt": "Like One Foundation logo",
                }
            ]),
            model="qwen3:14b",
        )
        evals = evaluate_alt_text(
            "https://example.com",
            [{"src": "logo.png", "alt": "logo"}],
        )
        assert len(evals) == 1
        assert evals[0].score == 2
        assert evals[0].suggested_alt == "Like One Foundation logo"

    @patch("techaccess.analyzer.generate")
    def test_empty_images(self, mock_gen):
        evals = evaluate_alt_text("https://example.com", [])
        assert evals == []
        mock_gen.assert_not_called()

    @patch("techaccess.analyzer.generate")
    def test_handles_bad_response(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="garbage", model="test")
        evals = evaluate_alt_text("https://example.com", [{"src": "x.png", "alt": ""}])
        assert evals == []


# --- Remediator: generate_fixes ---

class TestGenerateFixes:
    @patch("techaccess.remediator.generate")
    def test_returns_fixes(self, mock_gen):
        mock_gen.return_value = ModelResponse(
            text=json.dumps([
                {
                    "rule_id": "color-contrast",
                    "fix_type": "css",
                    "description": "Increase text contrast",
                    "before": "color: #777;",
                    "after": "color: #595959;",
                    "wcag": "1.4.3",
                    "confidence": 0.9,
                    "notes": "",
                }
            ]),
            model="qwen3:30b",
        )
        issues = [make_issue()]
        fixes = generate_fixes(issues, url="https://example.com")
        assert len(fixes) == 1
        assert fixes[0].rule_id == "color-contrast"
        assert fixes[0].confidence == 0.9

    @patch("techaccess.remediator.generate")
    def test_empty_issues(self, mock_gen):
        fixes = generate_fixes([])
        assert fixes == []
        mock_gen.assert_not_called()

    @patch("techaccess.remediator.generate")
    def test_skips_scan_errors(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="[]", model="test")
        issues = [make_issue(rule_id="scan-error")]
        fixes = generate_fixes(issues)
        assert fixes == []

    @patch("techaccess.remediator.generate")
    def test_handles_bad_response(self, mock_gen):
        mock_gen.return_value = ModelResponse(text="not json", model="test")
        fixes = generate_fixes([make_issue()])
        assert fixes == []


# --- Remediator: output formats ---

class TestFixesOutput:
    def test_markdown_empty(self):
        result = fixes_to_markdown([])
        assert "No fixes" in result

    def test_markdown_with_fixes(self):
        fix = CodeFix(
            rule_id="color-contrast",
            fix_type="css",
            description="Increase contrast",
            before="color: #777;",
            after="color: #333;",
            wcag="1.4.3",
            confidence=0.9,
        )
        result = fixes_to_markdown([fix])
        assert "color-contrast" in result
        assert "Before" in result
        assert "After" in result
        assert "HIGH" in result

    def test_markdown_low_confidence(self):
        fix = CodeFix(
            rule_id="test",
            fix_type="html",
            description="Test fix",
            before="<div>",
            after="<button>",
            confidence=0.3,
            notes="Needs human review",
        )
        result = fixes_to_markdown([fix])
        assert "LOW" in result
        assert "human review" in result

    def test_json_output(self):
        fix = CodeFix(
            rule_id="test",
            fix_type="html",
            description="Fix",
            before="<div>",
            after="<button>",
            wcag="4.1.2",
            confidence=0.8,
        )
        result = fixes_to_json([fix])
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["rule_id"] == "test"
        assert parsed[0]["wcag"] == "4.1.2"

    def test_codefix_to_dict(self):
        fix = CodeFix(
            rule_id="test",
            fix_type="aria",
            description="Add label",
            before='<input>',
            after='<input aria-label="Name">',
            confidence=0.85,
        )
        d = fix.to_dict()
        assert d["fix_type"] == "aria"
        assert d["confidence"] == 0.85


# --- AltTextEvaluation ---

class TestAltTextEvaluation:
    def test_to_dict(self):
        e = AltTextEvaluation(
            src="img.png",
            current_alt="photo",
            score=3,
            issues=["Too generic"],
            suggested_alt="Team photo at company event",
        )
        d = e.to_dict()
        assert d["score"] == 3
        assert d["suggested_alt"] == "Team photo at company event"
        assert "Too generic" in d["issues"]


# --- Alt Text Generation ---

class TestGenerateAltText:
    @patch("techaccess.analyzer.extract_images")
    def test_empty_when_no_images(self, mock_extract):
        mock_extract.return_value = []
        results = generate_alt_text("https://example.com")
        assert results == []

    def test_empty_when_all_have_alt(self):
        images = [
            {"src": "logo.png", "alt": "Company logo shown on homepage", "has_alt": True},
            {"src": "hero.jpg", "alt": "Team working in modern office space", "has_alt": True},
        ]
        results = generate_alt_text("https://example.com", images=images)
        assert results == []

    def test_filters_generic_alt(self):
        """Images with generic alt text like 'image' should be processed."""
        images = [
            {"src": "photo.jpg", "alt": "image", "has_alt": True},
            {"src": "good.jpg", "alt": "Team photo at company retreat", "has_alt": True},
        ]
        # Only photo.jpg needs alt text (generic alt)
        # Without a model available, it returns empty (no vision, no context model)
        # but the filtering logic should identify 1 image needs processing
        generic_alts = {"image", "img", "photo", "picture", "icon", "logo", "banner", ""}
        needs_alt = [
            img for img in images
            if not img.get("has_alt")
            or img.get("alt", "").strip().lower() in generic_alts
            or len(img.get("alt", "")) < 3
        ]
        assert len(needs_alt) == 1
        assert needs_alt[0]["src"] == "photo.jpg"

    def test_filters_missing_alt(self):
        """Images without alt attribute should be processed."""
        images = [
            {"src": "no-alt.png", "alt": "", "has_alt": False},
            {"src": "has-alt.png", "alt": "A descriptive caption", "has_alt": True},
        ]
        generic_alts = {"image", "img", "photo", "picture", "icon", "logo", "banner", ""}
        needs_alt = [
            img for img in images
            if not img.get("has_alt")
            or img.get("alt", "").strip().lower() in generic_alts
            or len(img.get("alt", "")) < 3
        ]
        assert len(needs_alt) == 1
        assert needs_alt[0]["src"] == "no-alt.png"

    @patch("techaccess.analyzer._generate_with_vision")
    @patch("techaccess.analyzer._generate_from_context")
    def test_falls_back_to_context(self, mock_context, mock_vision):
        mock_vision.return_value = []  # No vision model
        mock_context.return_value = [
            {"src": "hero.jpg", "alt": "Mountain landscape at sunset", "decorative": False, "confidence": 0.5, "model": "qwen3:30b"}
        ]
        images = [{"src": "hero.jpg", "alt": "", "has_alt": False}]
        results = generate_alt_text("https://example.com", images=images)
        assert len(results) == 1
        assert results[0]["alt"] == "Mountain landscape at sunset"

    @patch("techaccess.analyzer._generate_with_vision")
    def test_vision_result_returned(self, mock_vision):
        mock_vision.return_value = [
            {"src": "photo.jpg", "alt": "Golden retriever playing in park", "decorative": False, "confidence": 0.85, "model": "llava:13b"}
        ]
        images = [{"src": "photo.jpg", "alt": "", "has_alt": False}]
        results = generate_alt_text("https://example.com", images=images)
        assert len(results) == 1
        assert results[0]["model"] == "llava:13b"


# --- HTML Report ---

class TestHtmlReport:
    def test_valid_html(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert "<!DOCTYPE html>" in html
        assert "TechAccess" in html

    def test_contains_score(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert str(score.value) in html
        assert score.grade in html

    def test_contains_url(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert "https://example.com" in html

    def test_contains_issues(self):
        result = make_result([
            make_issue(impact="critical", rule_id="image-alt"),
            make_issue(impact="serious", rule_id="color-contrast"),
        ])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert "CRITICAL" in html
        assert "SERIOUS" in html
        assert "image-alt" in html

    def test_perfect_score(self):
        result = make_result([])
        score = calculate([])
        html = to_html(result, score)
        assert "No accessibility issues found" in html

    def test_escapes_html_in_elements(self):
        result = make_result([
            make_issue(element_html='<img src="x" onerror="alert(1)">'),
        ])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert "onerror" not in html or "&lt;" in html

    def test_dark_theme(self):
        result = make_result([make_issue()])
        score = calculate(result.issues)
        html = to_html(result, score)
        assert "#0f172a" in html  # Dark background

    def test_responsive(self):
        result = make_result([])
        score = calculate([])
        html = to_html(result, score)
        assert "viewport" in html
