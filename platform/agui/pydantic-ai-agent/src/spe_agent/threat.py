"""POST /threat-score: how much a prompt looks like an attack, for the chat's indicator while typing.

The prompt is embedded with the configured embedding model (the LLM endpoint's `/embeddings`, the agent's
own key) and scored by `threat_model.json`: logistic regressions on that embedding, one general head and one
per category, trained by `platform/agui/threat-score/train.py`. Advisory only: nothing is blocked, and
nothing is written to the run log (a draft is scored many times before it is sent).

Every head's probability is mapped to 0-100 on its own thresholds, so the numbers compare across heads:
50 is the head's `elevated` threshold (5% of benign in-domain prompts score above it) and 75 its `high`
threshold (1%).
"""
from __future__ import annotations

import json
import math
from collections import OrderedDict
from importlib.resources import files
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import ThreatScoreCfg

MAX_TEXT_CHARS = 16_000    # the request's limit
EMBED_CHARS = 6_000        # what is embedded, as in training
CACHE_SIZE = 256
EMBED_TIMEOUT_S = 10.0


class ThreatScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class ThreatUnavailable(Exception):
    """The embedding could not be had (endpoint down, model unknown, wrong size)."""


def display(p: float, elevated: float, high: float) -> int:
    """A probability on the head's own scale: 0..elevated -> 0..50, elevated..high -> 50..75, high..1 -> 75..100."""
    if p < elevated:
        value = 50 * p / elevated if elevated > 0 else 50.0
    elif p < high:
        value = 50 + 25 * (p - elevated) / (high - elevated)
    else:
        value = 75 + 25 * (p - high) / (1 - high) if high < 1 else 100.0
    return max(0, min(100, round(value)))


def level(score: int) -> str:
    return "high" if score >= 75 else "elevated" if score >= 50 else "low"


class ThreatModel:
    def __init__(self, data: dict[str, Any]):
        self.dimensions: int = data["dimensions"]
        self.info = {"version": data["version"], "trained": data["trained"], "embedding_model": data["embedding_model"],
                     "training": data["training"]}
        self.heads: list[dict[str, Any]] = data["heads"]
        for head in self.heads:
            if len(head["weights"]) != self.dimensions:
                raise ValueError(f"threat model head {head['id']}: {len(head['weights'])} weights, not {self.dimensions}")
        if not self.heads or self.heads[0]["id"] != "general":
            raise ValueError("threat model: the first head must be 'general'")

    @classmethod
    def packaged(cls) -> "ThreatModel":
        return cls(json.loads(files("spe_agent").joinpath("threat_model.json").read_text()))

    def score(self, embedding: list[float]) -> dict[str, Any]:
        if len(embedding) != self.dimensions:
            raise ThreatUnavailable(f"the embedding has {len(embedding)} dimensions, the model needs {self.dimensions}")
        norm = math.sqrt(sum(v * v for v in embedding)) or 1.0
        x = [v / norm for v in embedding]
        scored = []
        for head in self.heads:
            z = sum(w * v for w, v in zip(head["weights"], x)) + head["bias"]
            p = 1 / (1 + math.exp(-z)) if z > -700 else 0.0
            value = display(p, head["elevated"], head["high"])
            scored.append({"id": head["id"], "label": head["label"], "score": value, "level": level(value),
                           "probability": round(p, 4), "examples": head["examples"], "auc": head["auc"]})
        general, categories = scored[0], scored[1:]
        categories.sort(key=lambda c: -c["score"])
        return {"score": general["score"], "level": general["level"], "probability": general["probability"],
                "categories": categories, "model": self.info}


class ThreatScorer:
    """Embeds and scores. `http` is the test seam; otherwise a client of its own, closed by `aclose`."""

    def __init__(self, cfg: ThreatScoreCfg, base_url: str, api_key: str, *, model: ThreatModel | None = None,
                 http: httpx.AsyncClient | None = None):
        self._cfg = cfg
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model or ThreatModel.packaged()
        self._http = http or httpx.AsyncClient(timeout=EMBED_TIMEOUT_S)
        self._owns_http = http is None
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _embed(self, text: str) -> list[float]:
        try:
            response = await self._http.post(self._url, headers=self._headers,
                                             json={"model": self._cfg.embedding_model, "input": [text]})
        except httpx.HTTPError as e:
            raise ThreatUnavailable(f"the embedding request failed: {type(e).__name__}") from e
        if response.status_code != 200:
            raise ThreatUnavailable(f"the embedding endpoint answered {response.status_code}")
        try:
            embedding = response.json()["data"][0]["embedding"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ThreatUnavailable("the embedding endpoint's answer has no embedding") from e
        if not isinstance(embedding, list) or not all(isinstance(v, (int, float)) for v in embedding):
            raise ThreatUnavailable("the embedding endpoint's answer has no embedding")
        return embedding

    async def score(self, text: str) -> dict[str, Any]:
        key = text[:EMBED_CHARS]
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        result = self._model.score(await self._embed(key))
        self._cache[key] = result
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return result
