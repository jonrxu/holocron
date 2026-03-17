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


class OpenAIAnalyzer:
    version = "openai-responses-v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 90,
        reasoning_effort: str = "low",
        urlopen: object = urllib.request.urlopen,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.urlopen = urlopen

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        request_body = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": paper_analysis_system_prompt(),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": paper_analysis_user_prompt(payload),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "holocron_paper_analysis",
                    "strict": True,
                    "schema": paper_analysis_schema(),
                }
            },
        }

        if self._supports_reasoning():
            request_body["reasoning"] = {"effort": self.reasoning_effort}

        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with self.urlopen(request, timeout=self.timeout_seconds) as response:
            payload_bytes = response.read()
        response_body = json.loads(payload_bytes.decode("utf-8"))
        response_text = self._extract_text(response_body)
        parsed = json.loads(response_text)
        result = coerce_analysis_result(
            parsed,
            version=f"{self.version}:{response_body.get('model', self.model)}",
        )
        return replace(result, confidence=max(0.0, min(result.confidence, 1.0)))

    def _supports_reasoning(self) -> bool:
        model = self.model.lower()
        return model.startswith(("gpt-5", "o1", "o3", "o4", "gpt-oss"))

    def _extract_text(self, response_body: dict[str, object]) -> str:
        output = response_body.get("output", [])
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                contents = item.get("content", [])
                if not isinstance(contents, list):
                    continue
                for content in contents:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") in {"output_text", "text"} and isinstance(
                        content.get("text"), str
                    ):
                        return content["text"]
        raise ValueError("OpenAI response did not contain structured text output.")
