from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from btflow.memory.record import MemoryRecord


@dataclass
class SearchOptions:
    k: int = 5
    mode: str = "hybrid"
    alpha: float = 0.6
    recency_weight: float = 0.0
    recency_half_life_s: float = 3600.0
    filter_fn: Optional[Callable[[MemoryRecord], bool]] = None
    filter_spec: Optional[Dict[str, Any]] = None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def simple_embedding(text: str, dim: int = 64) -> List[float]:
    vec = [0.0] * dim
    for i, char in enumerate(text.lower()):
        idx = ord(char) % dim
        vec[idx] += 1.0 / (1 + i * 0.01)

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def coerce_embedding(value: Any) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(x) for x in value]
    if hasattr(value, "tolist"):
        return [float(x) for x in value.tolist()]
    return [float(x) for x in value]


def normalize_vector(vec: List[float], normalize: bool = True) -> List[float]:
    if not normalize:
        return vec
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._doc_freq: Dict[str, int] = {}
        self._doc_len: List[int] = []
        self._tokenized: List[List[str]] = []
        self._avgdl = 0.0

    def add(self, tokens: List[str]) -> None:
        self._tokenized.append(tokens)
        self._doc_len.append(len(tokens))
        self._avgdl = sum(self._doc_len) / len(self._doc_len) if self._doc_len else 0.0
        seen = set(tokens)
        for term in seen:
            self._doc_freq[term] = self._doc_freq.get(term, 0) + 1

    def rebuild(self, tokenized_docs: List[List[str]]) -> None:
        self._doc_freq = {}
        self._doc_len = []
        self._tokenized = []
        for tokens in tokenized_docs:
            self.add(tokens)

    def score(self, query_tokens: List[str]) -> List[float]:
        if not self._tokenized:
            return []
        if not query_tokens:
            return [0.0] * len(self._tokenized)

        scores = [0.0] * len(self._tokenized)
        total_docs = len(self._tokenized)

        for q in query_tokens:
            df = self._doc_freq.get(q, 0)
            if df == 0:
                continue
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            for i, doc_tokens in enumerate(self._tokenized):
                tf = doc_tokens.count(q)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * (self._doc_len[i] / (self._avgdl or 1.0)))
                scores[i] += idf * ((tf * (self.k1 + 1)) / denom)

        return scores


class Retriever:
    def search(
        self,
        query: str,
        records: Sequence[MemoryRecord],
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryRecord]:
        raise NotImplementedError


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _build_filter_fn(spec: Optional[Dict[str, Any]]) -> Optional[Callable[[MemoryRecord], bool]]:
    if not spec:
        return None

    meta_spec = spec.get("metadata")
    created_after = spec.get("created_after")
    created_before = spec.get("created_before")
    text_contains = spec.get("text_contains")

    def _parse_ts(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    after_dt = _parse_ts(created_after)
    before_dt = _parse_ts(created_before)

    def _fn(record: MemoryRecord) -> bool:
        if meta_spec:
            for key, expected in meta_spec.items():
                if record.metadata.get(key) != expected:
                    return False
        if text_contains:
            if text_contains.lower() not in record.text.lower():
                return False
        if after_dt or before_dt:
            created = record.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if after_dt and created < after_dt:
                return False
            if before_dt and created > before_dt:
                return False
        return True

    return _fn


class HybridRetriever(Retriever):
    def __init__(
        self,
        embedder: Optional[Callable[[str], List[float]]] = None,
        normalize_embeddings: bool = True,
    ):
        self._embedder = embedder
        self._normalize_embeddings = normalize_embeddings

    def _embed(self, text: str) -> Optional[List[float]]:
        if self._embedder is None:
            return None
        embedding = coerce_embedding(self._embedder(text))
        if embedding is None:
            return None
        return normalize_vector(embedding, normalize=self._normalize_embeddings)

    def search(
        self,
        query: str,
        records: Sequence[MemoryRecord],
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryRecord]:
        if not records:
            return []
        if options is None:
            options = SearchOptions()

        k = max(1, options.k)

        use_mode = (options.mode or "hybrid").lower()
        if use_mode not in ("semantic", "keyword", "hybrid"):
            use_mode = "hybrid"
        if use_mode == "semantic" and self._embedder is None:
            use_mode = "keyword"

        filter_fn = options.filter_fn or _build_filter_fn(options.filter_spec)
        if filter_fn is not None:
            filtered_records = [r for r in records if filter_fn(r)]
        else:
            filtered_records = list(records)

        if not filtered_records:
            return []
        if not query:
            return list(filtered_records)[-k:]

        semantic_scores = [0.0] * len(filtered_records)
        keyword_scores = [0.0] * len(filtered_records)

        if use_mode in ("semantic", "hybrid") and self._embedder is not None:
            query_vec = self._embed(query)
            if query_vec is not None:
                for i, record in enumerate(filtered_records):
                    if record.embedding is None:
                        record.embedding = self._embed(record.text)
                    if record.embedding is not None:
                        semantic_scores[i] = cosine_similarity(query_vec, record.embedding)

        if use_mode in ("keyword", "hybrid"):
            bm25 = BM25Index()
            tokenized = [_tokenize(r.text) for r in filtered_records]
            bm25.rebuild(tokenized)
            scores = bm25.score(_tokenize(query))
            keyword_scores = scores

        if semantic_scores:
            max_sem = max(semantic_scores) or 1.0
            semantic_scores = [s / max_sem for s in semantic_scores]
        if keyword_scores:
            max_kw = max(keyword_scores) or 1.0
            keyword_scores = [s / max_kw for s in keyword_scores]

        combined: List[tuple[float, MemoryRecord]] = []
        for i, record in enumerate(filtered_records):
            if use_mode == "semantic":
                score = semantic_scores[i]
            elif use_mode == "keyword":
                score = keyword_scores[i]
            else:
                score = options.alpha * semantic_scores[i] + (1 - options.alpha) * keyword_scores[i]

            if options.recency_weight > 0:
                created = record.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_s = (datetime.now(timezone.utc) - created).total_seconds()
                decay = math.exp(-age_s / max(options.recency_half_life_s, 1.0))
                score += options.recency_weight * decay

            combined.append((score, record))

        if not combined:
            return list(filtered_records)[-k:]

        if all(score <= 0 for score, _ in combined):
            return list(filtered_records)[-k:]

        combined.sort(key=lambda x: x[0], reverse=True)
        return [record for _, record in combined[:k]]


__all__ = [
    "SearchOptions",
    "Retriever",
    "HybridRetriever",
    "cosine_similarity",
    "simple_embedding",
    "coerce_embedding",
    "normalize_vector",
]
