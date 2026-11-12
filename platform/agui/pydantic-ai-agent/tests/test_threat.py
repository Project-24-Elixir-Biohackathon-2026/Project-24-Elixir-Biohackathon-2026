"""POST /threat-score: auth, the disabled flag, the embedding call, the scores and the failures."""
from __future__ import annotations

import json

import httpx
import pytest

from spe_agent.config import Config
from spe_agent.threat import ThreatModel, ThreatUnavailable, display, level
from spe_agent.app import create_app
from spe_agent.sandbox import SandboxClient
from test_app import (
    AGENT_KEY, AUTH, LLM_KEY, SANDBOX, SANDBOX_KEY, SECRETS, FakeSandbox, build, config, one_tool_then_answer, running,
)

BASE = "https://llm.example/v1"
MODEL = {"provider": "openai_compatible", "name": "m", "base_url": BASE}
ON = {"model": MODEL, "threat_score": {"enabled": True}}
DIMENSIONS = ThreatModel.packaged().dimensions


class FakeEmbeddings:
    def __init__(self, embedding=None, status=200, body=None):
        self.embedding = embedding if embedding is not None else [0.01] * DIMENSIONS
        self.status, self.body = status, body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, text=f"denied for key {LLM_KEY}")
        return httpx.Response(200, json=self.body if self.body is not None else {"data": [{"index": 0, "embedding": self.embedding}]})


def scoring(tmp_path, embeddings: FakeEmbeddings, secrets=SECRETS, **over):
    # Not test_app.build: its `model` argument is the scripted LLM, and here `model` is the configuration's.
    sandbox = SandboxClient(SANDBOX, SANDBOX_KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(FakeSandbox())))
    return create_app(config(tmp_path, **{**ON, **over}), secrets, model_override=one_tool_then_answer(),
                      sandbox_client=sandbox, threat_http=httpx.AsyncClient(transport=httpx.MockTransport(embeddings)),
                      retry_delay=0.01, probe_interval=0.05)


async def test_another_endpoint_gets_its_own_key(tmp_path):
    fake = FakeEmbeddings()
    secrets = SECRETS.model_copy(update={"threat_api_key": "sk-embeddings-only"})
    over = {"threat_score": {"enabled": True, "base_url": "https://embed.example/v1/"}}
    async with running(scoring(tmp_path, fake, secrets=secrets, **over)) as c:
        r = await c.post("/threat-score", json={"text": "hello there"}, headers=AUTH)
    assert r.status_code == 200
    sent = fake.requests[0]
    assert str(sent.url) == "https://embed.example/v1/embeddings"
    assert sent.headers["authorization"] == "Bearer sk-embeddings-only"


async def test_no_auth_is_401(tmp_path):
    fake = FakeEmbeddings()
    async with running(scoring(tmp_path, fake)) as c:
        r = await c.post("/threat-score", json={"text": "hello"})
    assert r.status_code == 401
    assert fake.requests == []


async def test_disabled_by_default_is_404(tmp_path):
    app, _ = build(tmp_path)
    async with running(app) as c:
        r = await c.post("/threat-score", json={"text": "hello"}, headers=AUTH)
    assert r.status_code == 404


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "x" * 16_001}, {"text": "a", "extra": 1}, {"text": 3}])
async def test_bad_body_is_422(tmp_path, body):
    fake = FakeEmbeddings()
    async with running(scoring(tmp_path, fake)) as c:
        r = await c.post("/threat-score", json=body, headers=AUTH)
    assert r.status_code == 422
    assert fake.requests == []


async def test_scores_without_waiting_for_the_sandbox_and_writes_no_run_log(tmp_path):
    fake = FakeEmbeddings()
    async with running(scoring(tmp_path, fake)) as c:
        r = await c.post("/threat-score", json={"text": "x" * 7000}, headers=AUTH)
        again = await c.post("/threat-score", json={"text": "x" * 7000}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["score"] <= 100 and body["level"] in ("low", "elevated", "high")
    assert [c["id"] for c in body["categories"]] and "general" not in [c["id"] for c in body["categories"]]
    assert body["categories"] == sorted(body["categories"], key=lambda c: -c["score"])
    assert set(body["categories"][0]) == {"id", "label", "score", "level", "probability", "examples", "auc"}
    assert body["model"]["embedding_model"] == "BAAI/bge-m3"
    # One embedding request for the two identical drafts: the configured model, the LLM key, the first 6000 characters.
    assert again.json() == body and len(fake.requests) == 1
    sent = fake.requests[0]
    assert str(sent.url) == f"{BASE}/embeddings" and sent.headers["authorization"] == f"Bearer {LLM_KEY}"
    assert json.loads(sent.content) == {"model": "vllm/BAAI/bge-m3", "input": ["x" * 6000]}
    assert not (tmp_path / "log" / "runs.jsonl").exists()


async def test_a_weight_direction_scores_high(tmp_path):
    """An embedding along the general head's weights is as adversarial as the model can see."""
    weights = ThreatModel.packaged().heads[0]["weights"]
    async with running(scoring(tmp_path, FakeEmbeddings(embedding=weights))) as c:
        high = (await c.post("/threat-score", json={"text": "a"}, headers=AUTH)).json()
    async with running(scoring(tmp_path, FakeEmbeddings(embedding=[-w for w in weights]))) as c:
        low = (await c.post("/threat-score", json={"text": "a"}, headers=AUTH)).json()
    assert high["level"] == "high" and high["score"] >= 75
    assert low["level"] == "low" and low["score"] < 50


@pytest.mark.parametrize("fake", [FakeEmbeddings(status=500), FakeEmbeddings(body={"data": []}),
                                  FakeEmbeddings(embedding=[0.1] * 8), FakeEmbeddings(body={"data": [{"embedding": "x"}]})])
async def test_embedding_failure_is_502_without_the_key(tmp_path, fake):
    async with running(scoring(tmp_path, fake)) as c:
        r = await c.post("/threat-score", json={"text": "hello"}, headers=AUTH)
    assert r.status_code == 502
    assert LLM_KEY not in r.text and AGENT_KEY not in r.text


async def test_own_base_url(tmp_path):
    fake = FakeEmbeddings()
    app = scoring(tmp_path, fake, threat_score={"enabled": True, "base_url": "https://emb.example/v1/", "embedding_model": "bge"})
    async with running(app) as c:
        await c.post("/threat-score", json={"text": "hello"}, headers=AUTH)
    assert str(fake.requests[0].url) == "https://emb.example/v1/embeddings"
    assert json.loads(fake.requests[0].content)["model"] == "bge"


def test_enabled_needs_an_openai_compatible_provider():
    base = {"prompt": {"file": "p"}, "tools": {"sandbox_url": "http://s"}, "threat_score": {"enabled": True}}
    with pytest.raises(ValueError, match="openai_compatible"):
        Config.model_validate({**base, "model": {"provider": "anthropic", "name": "claude-haiku-5-5"}})
    Config.model_validate({**base, "model": MODEL})


def test_display_scale():
    assert display(0, 0.2, 0.5) == 0 and display(0.1, 0.2, 0.5) == 25
    assert display(0.2, 0.2, 0.5) == 50 and display(0.35, 0.2, 0.5) == 62
    assert display(0.5, 0.2, 0.5) == 75 and display(1, 0.2, 0.5) == 100
    assert [level(s) for s in (0, 49, 50, 74, 75, 100)] == ["low", "low", "elevated", "elevated", "high", "high"]


def test_wrong_dimensions_is_unavailable():
    with pytest.raises(ThreatUnavailable):
        ThreatModel.packaged().score([0.1, 0.2])
