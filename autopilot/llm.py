"""Minimal Gemini client (REST) that returns parsed JSON."""
import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Models that returned 404 this run (retired / not available to this key) are skipped next time.
_unavailable: set[str] = set()


def generate_json(prompt: str, models, temperature: float = 0.9, retries: int = 5) -> dict:
    """models: a model name or a list tried in order; a 404 moves on to the next one."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if isinstance(models, str):
        models = [models]

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    errors = []
    for model in [m for m in models if m not in _unavailable]:
        last_error = ""
        for attempt in range(retries):
            r = requests.post(
                API.format(model=model),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=180,
            )
            if r.status_code == 404:
                _unavailable.add(model)
                print(f"Gemini model '{model}' not available (404), trying the next one", flush=True)
                last_error = "404 not found"
                break
            if r.status_code in (429, 500, 502, 503, 504):
                last_error = f"{r.status_code}: {r.text[:300]}"
                time.sleep(15 * (attempt + 1))  # free tier is rate-limited per minute
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini error {r.status_code} for {model}: {r.text[:500]}")
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
        errors.append(f"{model}: {last_error}")
    raise RuntimeError("All Gemini models failed — " + " | ".join(errors or ["no models left to try"]))


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
