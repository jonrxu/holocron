from __future__ import annotations

import json
import unittest

from holocron.qa import GeminiAnswerer, PaperChunk, split_text_into_chunks

from support import FakeHTTPResponse


class ChunkingTests(unittest.TestCase):
    def test_split_text_into_chunks_preserves_multiple_sections(self) -> None:
        text = (
            "Abstract\n\n"
            "This is the first section about retrieval and ranking.\n\n"
            "Method\n\n"
            "This section describes the model and the evaluation setup.\n\n"
            "Results\n\n"
            "This section reports the strongest benchmark result."
        )

        chunks = split_text_into_chunks(text, max_chars=90, overlap_chars=20)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("retrieval and ranking", chunks[0])


class GeminiAnswererTests(unittest.TestCase):
    def test_gemini_answerer_parses_generate_content_response(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=0):  # noqa: ANN001
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "The paper improves retrieval quality by using a stronger encoder. [1]"
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        answerer = GeminiAnswerer(
            api_key="test-key",
            model="gemini-2.5-flash-lite",
            opener=fake_urlopen,
        )

        result = answerer.answer_question(
            "Transformer Retrieval",
            "What does the paper improve?",
            [PaperChunk(chunk_index=3, text="The encoder improves retrieval quality.", score=0.91)],
        )

        self.assertEqual(result.model, "gemini-2.5-flash-lite")
        self.assertIn("improves retrieval quality", result.answer)
        self.assertIn("generateContent", captured["url"])
        self.assertEqual(captured["timeout"], 30)
