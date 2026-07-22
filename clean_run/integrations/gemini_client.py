from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


GEMINI_MODEL = "models/gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent"
)
CLEAN_RUN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(env_path: str | Path) -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def get_gemini_api_key() -> str:
    candidate_env_files = [
        CLEAN_RUN_ROOT / ".env",
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "google_routes" / ".env",
    ]
    for env_path in candidate_env_files:
        load_env_file(env_path)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing GEMINI_API_KEY. Add it to your environment or .env file."
        )
    return api_key


def generate_structured_json(
    *,
    prompt: str,
    response_schema: dict[str, Any],
    temperature: float = 0.2,
    timeout: int = 60,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": get_gemini_api_key(),
    }
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseJsonSchema": response_schema,
        },
    }

    response = requests.post(
        GEMINI_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned no content parts.")

    text = parts[0].get("text")
    if not text:
        raise RuntimeError("Gemini returned no JSON text content.")

    return json.loads(text)


def generate_markdown_text(
    *,
    prompt: str,
    temperature: float = 0.35,
    timeout: int = 90,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": get_gemini_api_key(),
    }
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    response = requests.post(
        GEMINI_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned no content parts.")

    text = parts[0].get("text")
    if not text:
        raise RuntimeError("Gemini returned no text content.")
    return text

def generate_chat_response(
    *,
    messages: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.35,
    timeout: int = 90,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": get_gemini_api_key(),
    }

    formatted_contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        formatted_contents.append({
            "role": role,
            "parts": [{"text": m["content"]}]
        })

    payload = {
        "contents": formatted_contents,
        "generationConfig": {
            "temperature": temperature,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}],
        }

    response = requests.post(
        GEMINI_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned no content parts.")

    text = parts[0].get("text")
    if not text:
        raise RuntimeError("Gemini returned no text content.")
    return text
