from __future__ import annotations

import json
import urllib.request
from dataclasses import replace

from .analysis_common import (
    AnalysisInput,
    AnalysisResult,
    coerce_analysis_result,
    paper_analysis_schema,
    paper_analysis_system_prompt,
    paper_analysis_user_prompt,
)


class GeminiAnalyzer:
    version = "gemini-generate-content-v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: int = 60,
        opener: object = urllib.request.urlopen,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        request_body = {
            "system_instruction": {
                "parts": [
                    {
                        "text": paper_analysis_system_prompt(),
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": paper_analysis_user_prompt(payload),
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseJsonSchema": paper_analysis_schema(),
            },
        }

        request = urllib.request.Request(
            f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.opener(request, timeout=self.timeout_seconds) as response:
            payload_bytes = response.read()
        response_body = json.loads(payload_bytes.decode("utf-8"))
        response_text = self._extract_text(response_body)
        parsed = json.loads(response_text)
        result = coerce_analysis_result(
            parsed,
            version=f"{self.version}:{self.model}",
        )
        return replace(result, confidence=max(0.0, min(result.confidence, 1.0)))

    def _extract_text(self, response_body: dict[str, object]) -> str:
        candidates = response_body.get("candidates", [])
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get("content", {})
                if not isinstance(content, dict):
                    continue
                parts = content.get("parts", [])
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        return part["text"]
        raise ValueError("Gemini response did not contain structured text output.")
