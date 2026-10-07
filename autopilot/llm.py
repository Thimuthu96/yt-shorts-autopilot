"""Minimal Gemini client (REST) that returns parsed JSON."""
import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def generate_json(prompt: str, model: str, temperature: float = 0.9, retries: int = 5) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    last_error = ""
    for attempt in range(retries):
        r = requests.post(
            API.format(model=model),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=180,
        )
        if r.status_code in (429, 500, 502, 503, 504):
            last_error = f"{r.status_code}: {r.text[:300]}"
            time.sleep(15 * (attempt + 1))  # free tier is rate-limited per minute
            continue
        r.raise_for_status()
        data = r.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            last_error = f"empty response: {json.dumps(data)[:300]}"
            time.sleep(5)
            continue
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        try:
            return json.loads(_strip_fences(text))
        except json.JSONDecodeError:
            last_error = f"invalid JSON: {text[:300]}"
            continue
    raise RuntimeError(f"Gemini request failed after {retries} attempts ({last_error})")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
