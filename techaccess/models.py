"""TechAccess AI Model Layer — Local-first, cloud-optional.

Unified interface for AI inference:
- Ollama for local models (qwen3:30b, llava for vision)
- Claude API for cloud inference (optional, higher accuracy)
"""

import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx

OLLAMA_URL = "http://localhost:11434"

DEFAULTS = {
    "analysis": "qwen3:30b",
    "remediation": "qwen3:30b",
    "alttext": "llava:13b",
    "evaluation": "qwen3:14b",
}


@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_used: int = 0


def ollama_generate(
    prompt: str,
    model: str = "qwen3:30b",
    system: str = "",
    images: list[str] | None = None,
    timeout: float = 120.0,
) -> ModelResponse:
    """Generate text using Ollama local model."""
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4096},
    }
    if system:
        body["system"] = system
    if images:
        body["images"] = images

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{OLLAMA_URL}/api/generate", json=body)
        resp.raise_for_status()
        data = resp.json()

    return ModelResponse(
        text=data.get("response", ""),
        model=model,
        tokens_used=data.get("eval_count", 0),
    )


def ollama_available(model: str = "qwen3:30b") -> bool:
    """Check if Ollama is running and model is available."""
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            prefix = model.split(":")[0]
            return any(prefix in m for m in models)
    except Exception:
        return False


def claude_generate(
    prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    system: str = "",
    images: list[dict] | None = None,
    timeout: float = 120.0,
) -> ModelResponse:
    """Generate text using Claude API (cloud, optional)."""
    content: list[dict] = []

    if images:
        for img in images:
            content.append({"type": "image", "source": img})

    content.append({"type": "text", "text": prompt})

    body: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    return ModelResponse(
        text=text,
        model=model,
        tokens_used=data.get("usage", {}).get("output_tokens", 0),
    )


def generate(
    prompt: str,
    task: str = "analysis",
    system: str = "",
    images: list[str] | None = None,
    claude_api_key: str | None = None,
    prefer_cloud: bool = False,
) -> ModelResponse:
    """Unified generate — local Ollama first, cloud Claude fallback.

    Args:
        prompt: The prompt text
        task: Task type for model selection (analysis, remediation, alttext, evaluation)
        system: System prompt
        images: Base64-encoded images (for vision tasks)
        claude_api_key: Claude API key (enables cloud fallback)
        prefer_cloud: If True, try Claude first
    """
    local_model = DEFAULTS.get(task, "qwen3:30b")

    if prefer_cloud and claude_api_key:
        try:
            cloud_images = None
            if images:
                cloud_images = [
                    {"type": "base64", "media_type": "image/png", "data": img}
                    for img in images
                ]
            return claude_generate(
                prompt, claude_api_key, system=system, images=cloud_images
            )
        except Exception:
            pass

    if ollama_available(local_model):
        try:
            return ollama_generate(
                prompt, model=local_model, system=system, images=images
            )
        except Exception:
            pass

    if claude_api_key and not prefer_cloud:
        cloud_images = None
        if images:
            cloud_images = [
                {"type": "base64", "media_type": "image/png", "data": img}
                for img in images
            ]
        return claude_generate(
            prompt, claude_api_key, system=system, images=cloud_images
        )

    raise RuntimeError(
        f"No AI model available. Start Ollama with '{local_model}' "
        "or set CLAUDE_API_KEY / pass --claude-key."
    )


def extract_json(text: str) -> str:
    """Extract JSON from LLM response that may contain markdown or thinking."""
    # Strip qwen3 thinking tags first
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    if text.startswith("[") or text.startswith("{"):
        return text

    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        return match.group(1).strip()

    for start, end in [("[", "]"), ("{", "}")]:
        idx_start = text.find(start)
        idx_end = text.rfind(end)
        if idx_start >= 0 and idx_end > idx_start:
            return text[idx_start : idx_end + 1]

    return text
