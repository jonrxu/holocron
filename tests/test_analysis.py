from __future__ import annotations

import json
import unittest
from pathlib import Path

from holocron.analysis import AnalysisInput, FallbackAnalyzer, OpenAIAnalyzer
from holocron.service import HolocronService

from support import FakeHTTPResponse, make_settings


class OpenAIAnalyzerTests(unittest.TestCase):
    def test_openai_analyzer_parses_structured_json_output(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=0):  # noqa: ANN001
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "model": "gpt-5",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "summary_short": "Concise paper summary.",
                                            "summary_long": "Longer structured paper summary.",
                                            "why_it_matters": "Important for retrieval workflows.",
                                            "method_summary": "Uses a transformer encoder.",
                                            "limitations": ["Narrow evaluation scope."],
                                            "claims": ["Improves ranking quality."],
                                            "datasets": ["ArxivBench"],
                                            "tasks": ["retrieval"],
                                            "tags": ["domain:ml", "paper_type:methods"],
                                            "followup_questions": ["What stronger baseline should be added?"],
                                            "confidence": 0.91,
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                }
            )

        analyzer = OpenAIAnalyzer(
            api_key="test-key",
            model="gpt-5",
            urlopen=fake_urlopen,
        )

        result = analyzer.analyze(
            AnalysisInput(
                title="Transformer Retrieval",
                authors=["A. Ranker"],
                year=2024,
                abstract="Transformer retrieval for scientific search.",
                full_text="Transformer retrieval improves ranking on ArxivBench.",
            )
        )

        self.assertEqual(result.summary_short, "Concise paper summary.")
        self.assertIn("task:retrieval", result.tags)
        self.assertIn("status:unread", result.tags)
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["body"]["model"], "gpt-5")
        self.assertEqual(captured["body"]["reasoning"]["effort"], "low")

    def test_service_prefers_openai_analyzer_when_api_key_present(self) -> None:
        settings = make_settings(
            Path("/tmp/holocron-test-data"),
            openai_api_key="test-key",
            openai_model="gpt-5",
        )
        service = HolocronService(settings, worker_enabled=False)
        self.assertIsInstance(service.analyzer, FallbackAnalyzer)
