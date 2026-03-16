from __future__ import annotations

import json
import urllib.request
from dataclasses import replace

from .analysis_common import AnalysisInput, AnalysisResult, coerce_analysis_result


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
                            "text": self._system_prompt(),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._user_prompt(payload),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "holocron_paper_analysis",
                    "strict": True,
                    "schema": self._schema(),
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

    def _system_prompt(self) -> str:
        return (
            "You analyze scientific papers for a personal research memory. "
            "Return concise, factual structured JSON only. "
            "Use neutral academic language. "
            "Infer tasks, datasets, and typed tags only when the text supports them. "
            "Always include status:unread in tags. "
            "Allowed tag families: domain:*, paper_type:*, status:*, quality:*, needs:*, has:*, task:*."
        )

    def _user_prompt(self, payload: AnalysisInput) -> str:
        title = payload.title or "Unknown title"
        authors = ", ".join(payload.authors) if payload.authors else "Unknown authors"
        year = str(payload.year) if payload.year else "Unknown year"
        abstract = payload.abstract or "No abstract extracted."
        return (
            f"Title: {title}\n"
            f"Authors: {authors}\n"
            f"Year: {year}\n"
            f"Abstract:\n{abstract}\n\n"
            "Paper text:\n"
            f"{payload.full_text}\n\n"
            "Return a concise analysis that is useful for search, recall, and building relations "
            "between papers in a local library."
        )

    def _schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "summary_short",
                "summary_long",
                "why_it_matters",
                "method_summary",
                "limitations",
                "claims",
                "datasets",
                "tasks",
                "tags",
                "followup_questions",
                "confidence",
            ],
            "properties": {
                "summary_short": {"type": "string"},
                "summary_long": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "method_summary": {"type": "string"},
                "limitations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "claims": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "datasets": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "followup_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
        }
