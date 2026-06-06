"""TechAccess Analyzer — AI-powered accessibility analysis.

Three capabilities:
1. Semantic ARIA analysis — finds issues that rules miss
2. Alt text generation — context-aware alt text for images
3. Alt text evaluation — quality assessment of existing alt text
"""

import json
from dataclasses import dataclass, field

from .models import generate, extract_json
from .scanner import ScanResult, Issue


SEMANTIC_SYSTEM = (
    "You are an expert accessibility auditor. You analyze ARIA accessibility trees "
    "to find issues that automated rule-based tools miss.\n\n"
    "Focus on:\n"
    "- Missing or misleading ARIA labels\n"
    "- Incorrect heading hierarchy\n"
    "- Non-descriptive link text ('click here', 'read more')\n"
    "- Missing landmarks (main, nav, footer)\n"
    "- Incorrect ARIA roles\n"
    "- Form fields without associated labels\n"
    "- Reading order issues\n"
    "- Redundant ARIA attributes\n\n"
    "Output valid JSON only. No markdown fences, no explanation outside JSON."
)

SEMANTIC_PROMPT = """Analyze this ARIA accessibility tree for WCAG 2.2 AA issues that automated tools miss.

URL: {url}

ARIA Tree:
{aria_tree}

Existing violations (already caught -- do NOT duplicate):
{existing_issues}

Find NEW issues not in the existing list. Return JSON array:
[
  {{
    "rule_id": "semantic-<short-id>",
    "wcag": "<criterion like 1.3.1>",
    "impact": "critical|serious|moderate|minor",
    "description": "<clear description>",
    "element": "<the element or text involved>",
    "fix": "<specific fix recommendation>"
  }}
]

Return empty array [] if no new issues found."""


EVALUATE_SYSTEM = (
    "You are an accessibility expert evaluating alt text quality.\n"
    "Rate each image's alt text on a 1-5 scale:\n"
    "5 = Excellent: descriptive, concise, context-aware\n"
    "4 = Good: adequate but could be improved\n"
    "3 = Fair: functional but generic\n"
    "2 = Poor: misleading or too vague\n"
    "1 = Bad: wrong, missing, or harmful\n\n"
    "Output valid JSON only."
)

EVALUATE_PROMPT = """Evaluate alt text quality for images on this page.

URL: {url}

Images:
{images_json}

Page context (ARIA tree excerpt):
{context}

Return JSON array:
[
  {{
    "src": "<image src>",
    "current_alt": "<current alt text>",
    "score": 1-5,
    "issues": ["<issue1>"],
    "suggested_alt": "<improved alt text if score < 4>"
  }}
]"""


@dataclass
class AltTextEvaluation:
    src: str
    current_alt: str
    score: int
    issues: list[str] = field(default_factory=list)
    suggested_alt: str = ""

    def to_dict(self) -> dict:
        return {
            "src": self.src,
            "current_alt": self.current_alt,
            "score": self.score,
            "issues": self.issues,
            "suggested_alt": self.suggested_alt,
        }


def analyze_aria(
    scan_result: ScanResult,
    claude_api_key: str | None = None,
) -> list[Issue]:
    """Analyze ARIA tree for semantic issues that rules miss.

    Returns Issues that can be merged into scan results.
    """
    if not scan_result.aria_tree or not scan_result.aria_tree.get("content"):
        return []

    tree_content = scan_result.aria_tree["content"]
    if len(tree_content) > 8000:
        tree_content = tree_content[:8000] + "\n... (truncated)"

    existing = json.dumps(
        [
            {"rule_id": i.rule_id, "description": i.description[:80]}
            for i in scan_result.issues[:20]
        ],
        indent=1,
    )

    prompt = SEMANTIC_PROMPT.format(
        url=scan_result.url,
        aria_tree=tree_content,
        existing_issues=existing,
    )

    response = generate(
        prompt,
        task="analysis",
        system=SEMANTIC_SYSTEM,
        claude_api_key=claude_api_key,
    )

    issues = []
    try:
        parsed = json.loads(extract_json(response.text))
        if not isinstance(parsed, list):
            return []
        for item in parsed:
            issues.append(
                Issue(
                    rule_id=item.get("rule_id", "semantic-unknown"),
                    wcag=item.get("wcag", ""),
                    impact=item.get("impact", "moderate"),
                    description=item.get("description", ""),
                    element_html=item.get("element", ""),
                    selector="",
                    viewport="all",
                    source="ai-semantic",
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return issues


def evaluate_alt_text(
    url: str,
    images: list[dict],
    aria_excerpt: str = "",
    claude_api_key: str | None = None,
) -> list[AltTextEvaluation]:
    """Evaluate quality of existing alt text on a page."""
    if not images:
        return []

    prompt = EVALUATE_PROMPT.format(
        url=url,
        images_json=json.dumps(images[:20], indent=1),
        context=aria_excerpt[:3000] if aria_excerpt else "Not available",
    )

    response = generate(
        prompt,
        task="evaluation",
        system=EVALUATE_SYSTEM,
        claude_api_key=claude_api_key,
    )

    results = []
    try:
        parsed = json.loads(extract_json(response.text))
        if not isinstance(parsed, list):
            return []
        for item in parsed:
            results.append(
                AltTextEvaluation(
                    src=item.get("src", ""),
                    current_alt=item.get("current_alt", ""),
                    score=item.get("score", 3),
                    issues=item.get("issues", []),
                    suggested_alt=item.get("suggested_alt", ""),
                )
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return results


GENERATE_SYSTEM = (
    "You are an accessibility expert generating alt text for images.\n"
    "Write concise, descriptive alt text that:\n"
    "- Describes the image's content and purpose\n"
    "- Uses the page context to understand the image's role\n"
    "- Is under 125 characters when possible\n"
    "- Avoids starting with 'Image of' or 'Photo of'\n"
    "- For decorative images, returns empty string\n"
    "- For charts/diagrams, describes the data or relationships\n\n"
    "Output valid JSON only."
)

GENERATE_PROMPT = """Generate alt text for these images from a web page.

URL: {url}

Page context (ARIA tree excerpt):
{context}

Images needing alt text:
{images_json}

For each image, return JSON array:
[
  {{
    "src": "<image src>",
    "alt": "<generated alt text>",
    "decorative": false,
    "confidence": 0.8,
    "reasoning": "<brief explanation of your choice>"
  }}
]"""


def generate_alt_text(
    url: str,
    images: list[dict] | None = None,
    aria_excerpt: str = "",
    claude_api_key: str | None = None,
) -> list[dict]:
    """Generate alt text for images on a page using AI vision.

    If images is None, extracts images from the URL automatically.
    Uses llava (vision model) when image data is available, falls back
    to text-based generation from page context.
    """
    if images is None:
        images = extract_images(url)

    if not images:
        return []

    # Filter to images that need alt text (missing, empty, or generic)
    generic_alts = {"image", "img", "photo", "picture", "icon", "logo", "banner", ""}
    needs_alt = [
        img for img in images
        if not img.get("has_alt")
        or img.get("alt", "").strip().lower() in generic_alts
        or len(img.get("alt", "")) < 3
    ]

    if not needs_alt:
        return []

    # Try vision-based generation first (captures screenshots of each image)
    vision_results = _generate_with_vision(url, needs_alt, aria_excerpt, claude_api_key)
    if vision_results:
        return vision_results

    # Fall back to text-based generation from context
    return _generate_from_context(url, needs_alt, aria_excerpt, claude_api_key)


def _generate_with_vision(
    url: str,
    images: list[dict],
    aria_excerpt: str,
    claude_api_key: str | None,
) -> list[dict]:
    """Generate alt text using vision model with actual image screenshots."""
    import base64

    from .models import generate as ai_generate, extract_json, ollama_available

    if not ollama_available("llava") and not claude_api_key:
        return []

    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(500)

        for img_info in images[:10]:  # Limit to 10 images per run
            try:
                src = img_info.get("src", "")
                if not src:
                    continue

                # Find the image element and screenshot it
                img_el = page.locator(f'img[src="{src}"]').first
                if not img_el.is_visible():
                    continue

                screenshot = img_el.screenshot(type="png")
                b64_img = base64.b64encode(screenshot).decode("utf-8")

                context_hint = ""
                if img_info.get("parent_tag"):
                    context_hint = f" (inside <{img_info['parent_tag']}>)"

                prompt = (
                    f"Describe this image for use as alt text on a web page.\n"
                    f"Page URL: {url}{context_hint}\n"
                    f"Current alt: \"{img_info.get('alt', '')}\"\n"
                    f"Write concise, descriptive alt text (under 125 chars). "
                    f"If decorative, say DECORATIVE.\n"
                    f"Respond with ONLY the alt text, nothing else."
                )

                response = ai_generate(
                    prompt,
                    task="alttext",
                    images=[b64_img],
                    claude_api_key=claude_api_key,
                )

                alt = response.text.strip().strip('"').strip("'")
                decorative = alt.upper() == "DECORATIVE"

                results.append({
                    "src": src,
                    "alt": "" if decorative else alt,
                    "decorative": decorative,
                    "confidence": 0.85,
                    "model": response.model,
                })

            except Exception:
                continue

        browser.close()

    return results


def _generate_from_context(
    url: str,
    images: list[dict],
    aria_excerpt: str,
    claude_api_key: str | None,
) -> list[dict]:
    """Generate alt text from page context (no vision, text-only fallback)."""
    prompt = GENERATE_PROMPT.format(
        url=url,
        context=aria_excerpt[:3000] if aria_excerpt else "Not available",
        images_json=json.dumps(
            [
                {
                    "src": img.get("src", ""),
                    "current_alt": img.get("alt", ""),
                    "parent_tag": img.get("parent_tag", ""),
                    "width": img.get("width", 0),
                    "height": img.get("height", 0),
                }
                for img in images[:20]
            ],
            indent=1,
        ),
    )

    response = generate(
        prompt,
        task="alttext",
        system=GENERATE_SYSTEM,
        claude_api_key=claude_api_key,
    )

    results = []
    try:
        parsed = json.loads(extract_json(response.text))
        if isinstance(parsed, list):
            for item in parsed:
                results.append({
                    "src": item.get("src", ""),
                    "alt": item.get("alt", ""),
                    "decorative": item.get("decorative", False),
                    "confidence": item.get("confidence", 0.5),
                    "model": response.model,
                })
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return results


def extract_images(url: str) -> list[dict]:
    """Extract images and their alt text from a page."""
    from playwright.sync_api import sync_playwright

    js = """() => {
        return Array.from(document.querySelectorAll('img')).map(img => ({
            src: img.src,
            alt: img.alt || '',
            has_alt: img.hasAttribute('alt'),
            width: img.naturalWidth,
            height: img.naturalHeight,
            role: img.getAttribute('role') || '',
            aria_label: img.getAttribute('aria-label') || '',
            parent_tag: img.parentElement ? img.parentElement.tagName.toLowerCase() : '',
            is_visible: img.getBoundingClientRect().width > 0,
        })).filter(img => img.is_visible && img.width > 1);
    }"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(500)
        images = page.evaluate(js)
        browser.close()

    return images
