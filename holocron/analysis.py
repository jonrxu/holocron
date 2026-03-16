from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import asdict, replace

from .analysis_common import AnalysisInput, AnalysisResult, coerce_analysis_result
from .analysis_heuristic import HeuristicAnalyzer
from .analysis_openai import OpenAIAnalyzer


class ExternalCommandAnalyzer:
    def __init__(self, command: str) -> None:
        self.command = command

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        result = subprocess.run(
            shlex.split(self.command),
            input=json.dumps(asdict(payload)),
            text=True,
            capture_output=True,
            check=True,
        )
        parsed = json.loads(result.stdout)
        return coerce_analysis_result(
            parsed,
            version=str(parsed.get("version", "external-command")),
        )


class FallbackAnalyzer:
    def __init__(self, primary: object, fallback: object, label: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.label = label

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        try:
            return self.primary.analyze(payload)
        except Exception:
            result = self.fallback.analyze(payload)
            return replace(result, version=f"{result.version}+fallback:{self.label}")


__all__ = [
    "AnalysisInput",
    "AnalysisResult",
    "ExternalCommandAnalyzer",
    "FallbackAnalyzer",
    "HeuristicAnalyzer",
    "OpenAIAnalyzer",
]
