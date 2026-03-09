from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Optional

import requests
from requests import RequestException

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class GroqResult:
    content: dict
    raw_text: str


class GroqService:
    def __init__(self, *, api_key: Optional[str], base_url: str, model: str, timeout_s: int = 35):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def _extract_json(self, text: str) -> dict:
        text = (text or "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_OBJECT_RE.search(text)
            if not match:
                raise
            return json.loads(match.group(0))

    def _post_chat(self, payload: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("missing_groq_api_key")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout_s)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 401:
                raise RuntimeError("groq_unauthorized") from e
            raise RuntimeError("groq_http_error") from e
        except RequestException as e:
            raise RuntimeError("groq_request_failed") from e

    def chat_json(self, *, system: str, user: str) -> GroqResult:
        payload = {
            "model": self.model,
            "temperature": 0.6,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }

        data = self._post_chat(payload)
        raw_text = data["choices"][0]["message"]["content"]
        parsed = self._extract_json(raw_text)
        return GroqResult(content=parsed, raw_text=raw_text)

    def chat_json_with_image(
        self,
        *,
        system: str,
        user_text: str,
        image_bytes: bytes,
        image_mime: str,
        model: Optional[str] = None,
    ) -> GroqResult:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{image_mime};base64,{b64}"

        payload = {
            "model": model or self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            # NOTE: response_format is intentionally omitted for vision models.
            # Most vision/multimodal models (including llama-4-scout) do NOT support
            # the json_object response_format and will return a 400 error if it's set.
            # We use _extract_json() to parse JSON from the raw text response instead.
        }

        data = self._post_chat(payload)
        raw_text = data["choices"][0]["message"]["content"]
        parsed = self._extract_json(raw_text)
        return GroqResult(content=parsed, raw_text=raw_text)