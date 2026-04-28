from __future__ import annotations

import json
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_s: float = 60.0


def ollama_generate(*, cfg: OllamaConfig, prompt: str) -> str:
    """
    Calls Ollama /api/generate with stream=false.
    Returns the model response text.
    """
    url = cfg.base_url.rstrip("/") + "/api/generate"
    payload = {"model": cfg.model, "prompt": prompt, "stream": False}
    with httpx.Client(timeout=cfg.timeout_s) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict) or "response" not in data:
        raise ValueError(f"Unexpected Ollama response: {json.dumps(data)[:2000]}")
    return str(data["response"]).strip()

