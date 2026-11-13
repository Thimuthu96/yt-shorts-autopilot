"""Minimal Gemini client (REST).

    generate_json(prompt, models, temperature=0.9) -> dict
    generate_text(prompt, models, tools=None, temperature=0.7, rounds=2) -> (text, groundingMetadata)
        tools=[{"google_search": {}}] grounds the answer with Google Search (free tier); no JSON mime type then.
"""
import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Models that returned 404 this run (retired / not available to this key) are skipped next time.
_unavailable: set[str] = set()


def generate_json(prompt: str, models, temperature: float = 0.9, retries: int = 4) -> dict:
    """models: a model name or a list tried in order.

    404 (retired) → skip that model for the rest of the run.
    500/503 (overloaded) → one quick retry, then the next model.
    429 (rate limit) → wait and retry the same model.
    If every model fails, wait a minute and go round the list once more.
    """
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
    return _run(models, key, body, retries, _parse_json, 2)


def generate_text(prompt: str, models, tools=None, temperature: float = 0.7, retries: int = 4,
                  rounds: int = 2) -> tuple[str, dict]:
    """Plain text + the candidate's groundingMetadata ({} when not grounded). Same retry / fallback rules as
    generate_json; `rounds=1` skips the 60 s wait and second round (e.g. a grounded call that has a fallback)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if isinstance(models, str):
        models = [models]
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if tools:
        body["tools"] = tools
    return _run(models, key, body, retries, _parse_text, rounds)


def _run(models, key, body, retries, parse, rounds):
    errors = []
    for round_no in range(rounds):
        if round_no:
            print("All Gemini models busy, waiting 60s before one more round", flush=True)
            time.sleep(60)
        for model in [m for m in models if m not in _unavailable]:
            result, error = _try_model(model, key, body, retries, parse)
            if result is not None:
                return result
            errors.append(f"{model}: {error}")
    raise RuntimeError("All Gemini models failed — " + " | ".join(errors[-6:] or ["no models left to try"]))


def _parse_json(text: str, cand: dict):
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        raise ValueError(f"invalid JSON: {text[:200]}")


def _parse_text(text: str, cand: dict):
    if not text.strip():
        raise ValueError("empty text")
    return text, cand.get("groundingMetadata") or {}


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]   gemini: {msg}", flush=True)


def _try_model(model: str, key: str, body: dict, retries: int, parse=_parse_json):
    last_error = ""
    for attempt in range(retries):
        started = time.time()
        _log(f"asking {model} (attempt {attempt + 1})")
        try:
            r = requests.post(
                API.format(model=model),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=(15, 120),  # connect, read
            )
        except requests.Timeout:
            _log(f"{model} gave no answer in 2 min, trying the next model")
            return None, "timeout"
        except requests.RequestException as e:
            last_error = f"network: {e}"
            _log(f"network error: {e}")
            time.sleep(10)
            continue
        _log(f"{model} replied {r.status_code} after {time.time() - started:.0f}s")
        if r.status_code == 404:
            _unavailable.add(model)
            print(f"Gemini model '{model}' not available (404), trying the next one", flush=True)
            return None, "404 not found"
        if r.status_code in (500, 502, 503, 504):
            last_error = f"{r.status_code} busy"
            if attempt >= 1:
                print(f"Gemini model '{model}' busy ({r.status_code}), trying the next one", flush=True)
                return None, last_error
            time.sleep(10)
            continue
        if r.status_code == 429:
            last_error = f"429 rate limit: {r.text[:200]}"
            if "PerDay" in r.text or "per day" in r.text.lower():
                _log(f"{model} daily free quota used up, trying the next model")
                return None, "daily quota used up"
            wait = 20 * (attempt + 1)
            _log(f"{model} rate limit hit, waiting {wait}s")
            time.sleep(wait)  # free tier is rate-limited per minute
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini error {r.status_code} for {model}: {r.text[:500]}")
        data = r.json()
        try:
            cand = data["candidates"][0]
            parts = cand["content"]["parts"]
        except (KeyError, IndexError):
            last_error = f"empty response: {json.dumps(data)[:200]}"
            time.sleep(5)
            continue
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        try:
            return parse(text, cand), ""
        except ValueError as e:
            last_error = str(e)
            continue
    return None, last_error


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
