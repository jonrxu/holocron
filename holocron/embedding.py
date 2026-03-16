from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable


def normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-12:
        return [0.0 for _ in values]
    return [value / norm for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+", text.lower())


def _orthogonalize(vector: list[float], basis: list[list[float]]) -> list[float]:
    result = list(vector)
    for component in basis:
        projection = sum(left * right for left, right in zip(result, component))
        result = [value - projection * axis for value, axis in zip(result, component)]
    return result


def _covariance_matvec(rows: list[list[float]], vector: list[float]) -> list[float]:
    result = [0.0 for _ in vector]
    for row in rows:
        weight = sum(value * axis for value, axis in zip(row, vector))
        for index, value in enumerate(row):
            result[index] += value * weight
    return result


def project_embeddings(vectors: list[list[float]]) -> list[tuple[float, float]]:
    if not vectors:
        return []
    if len(vectors) == 1:
        return [(0.0, 0.0)]

    dimensions = len(vectors[0])
    means = [sum(vector[index] for vector in vectors) / len(vectors) for index in range(dimensions)]
    centered = [
        [value - means[index] for index, value in enumerate(vector)]
        for vector in vectors
    ]

    if not any(any(abs(value) > 1e-9 for value in vector) for vector in centered):
        return _fallback_positions(len(vectors))

    basis: list[list[float]] = []
    seed_vectors = [
        [1.0 if index % 2 == 0 else 0.5 for index in range(dimensions)],
        [0.5 if index % 3 == 0 else -0.25 for index in range(dimensions)],
    ]

    for seed in seed_vectors:
        vector = normalize_vector(_orthogonalize(seed, basis))
        if not any(abs(value) > 1e-9 for value in vector):
            continue
        for _ in range(32):
            updated = _covariance_matvec(centered, vector)
            updated = _orthogonalize(updated, basis)
            vector = normalize_vector(updated)
            if not any(abs(value) > 1e-9 for value in vector):
                break
        if any(abs(value) > 1e-9 for value in vector):
            basis.append(vector)

    if not basis:
        return _fallback_positions(len(vectors))
    if len(basis) == 1:
        basis.append([0.0 for _ in range(dimensions)])

    coordinates = []
    for vector in centered:
        x = sum(value * basis[0][index] for index, value in enumerate(vector))
        y = sum(value * basis[1][index] for index, value in enumerate(vector))
        coordinates.append((x, y))

    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    span_x = max(max(xs) - min(xs), 1e-9)
    span_y = max(max(ys) - min(ys), 1e-9)
    return [
        (
            ((x - min(xs)) / span_x) * 2.0 - 1.0,
            ((y - min(ys)) / span_y) * 2.0 - 1.0,
        )
        for x, y in coordinates
    ]


def _fallback_positions(count: int) -> list[tuple[float, float]]:
    if count <= 1:
        return [(0.0, 0.0)] * count
    positions = []
    for index in range(count):
        angle = (math.pi * 2 * index) / count
        positions.append((math.cos(angle) * 0.72, math.sin(angle) * 0.72))
    return positions


@dataclass
class DocumentEmbeddingInput:
    title: str | None
    text: str


class LocalEmbeddingProvider:
    version = "local-hash-v1"

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions
        self._query_cache: OrderedDict[str, list[float]] = OrderedDict()

    def _embed(self, text: str) -> list[float]:
        vector = [0.0 for _ in range(self.dimensions)]
        for token in _tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            weight = 1.0 + ((digest[5] % 7) / 10.0)
            vector[index] += sign * weight
        return normalize_vector(vector)

    def embed_document(self, document: DocumentEmbeddingInput) -> list[float]:
        source = "\n".join(part for part in [document.title or "", document.text] if part).strip()
        return self._embed(source)

    def embed_query(self, query: str) -> list[float]:
        normalized = " ".join(query.split()).lower()
        if normalized in self._query_cache:
            return self._query_cache[normalized]
        embedding = self._embed(normalized)
        self._query_cache[normalized] = embedding
        while len(self._query_cache) > 128:
            self._query_cache.popitem(last=False)
        return embedding


class GeminiEmbeddingProvider:
    version = "gemini-embedding-001"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        output_dimensionality: int = 768,
        timeout_seconds: int = 30,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.output_dimensionality = output_dimensionality
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self._query_cache: OrderedDict[str, list[float]] = OrderedDict()

    def _request(self, payload: dict[str, object]) -> list[float]:
        request = urllib.request.Request(
            f"{self.base_url}/models/{self.model}:embedContent?key={self.api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        values = [float(value) for value in body["embedding"]["values"]]
        return normalize_vector(values)

    def embed_document(self, document: DocumentEmbeddingInput) -> list[float]:
        return self._request(
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": document.text}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "title": document.title or "",
                "outputDimensionality": self.output_dimensionality,
            }
        )

    def embed_query(self, query: str) -> list[float]:
        normalized = " ".join(query.split())
        if normalized in self._query_cache:
            return self._query_cache[normalized]
        embedding = self._request(
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": normalized}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": self.output_dimensionality,
            }
        )
        self._query_cache[normalized] = embedding
        while len(self._query_cache) > 128:
            self._query_cache.popitem(last=False)
        return embedding


class FallbackEmbeddingProvider:
    def __init__(self, primary: object, fallback: object) -> None:
        self.primary = primary
        self.fallback = fallback
        self.version = getattr(primary, "version", "primary")

    def embed_document(self, document: DocumentEmbeddingInput) -> list[float]:
        try:
            return self.primary.embed_document(document)
        except Exception:
            return self.fallback.embed_document(document)

    def embed_query(self, query: str) -> list[float]:
        try:
            return self.primary.embed_query(query)
        except Exception:
            return self.fallback.embed_query(query)
