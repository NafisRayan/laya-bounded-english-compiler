"""Unit tests for the baseline adapters (Developer Spec.md §4.2).

All LLM-backed paths are exercised with injected stub completers so the
harness is testable without API keys; the credential-gating behavior itself
is asserted by checking that the default adapters self-skip in a keyless
environment.
"""

from __future__ import annotations

import httpx

from tests.experiments import baselines
from tests.experiments.baselines import (
    BackendSpecBaseline,
    DirectSqlBaseline,
    gemini_completer,
    parse_backend_spec,
    score_baseline,
    table_names_from_sql,
)
from tests.experiments.metrics import extract_labels


def _stub_completer(text: str):
    class _Stub:
        name = "stub"
        calls = 0

        def complete(self, system: str, user: str) -> str:
            _Stub.calls += 1
            return text

    return _Stub()


def test_table_names_from_sql_parses_variants():
    sql = (
        "CREATE TABLE IF NOT EXISTS listings (id uuid);\n"
        "CREATE TABLE bookings (id uuid);\n"
        'CREATE TABLE "users" (id uuid);\n'
        "COMMENT ON TABLE listings IS 'x';\n"
    )
    assert table_names_from_sql(sql) == ["listings", "bookings", "users"]


def test_parse_backend_spec_happy_path(ontology):
    raw = '{"features": {"authentication": true, "bookings": true},' \
          ' "parameters": {"authentication.method": "email_password"}, ' \
          ' "roles": ["user", "owner"], "entities": ["users", "listings", "bookings"],' \
          ' "buckets": [], "edge_functions": []}'
    spec = parse_backend_spec(raw, ontology)
    assert spec is not None
    assert spec.features == {"authentication": True, "bookings": True}
    assert spec.roles == ["user", "owner"]
    # entities are derived by recompute_spec from the decided features
    assert {"profiles", "listings", "bookings"} <= set(spec.entities)


def test_parse_backend_spec_tolerates_fences_and_prose(ontology):
    fenced = 'Here is the spec:\n```json\n{"features": {"payments": true}}```\n'
    spec = parse_backend_spec(fenced, ontology)
    assert spec is not None and spec.features == {"payments": True}


def test_parse_backend_spec_returns_none_on_garbage(ontology):
    assert parse_backend_spec("not json at all", ontology) is None
    assert parse_backend_spec('[1, 2, 3]', ontology) is None
    assert parse_backend_spec('{"features": "oops"}', ontology) is None


def test_backend_spec_baseline_injected_completer_scores_against_labels(ontology):
    def cases():
        return [(
            "laya_high_decides",
            {
                "input": "Use stripe for payments and email password for login",
                "laya": "high",
                "expected_spec": {
                    "features": {"authentication": True, "payments": True},
                    "parameters": {
                        "authentication.method": "email_password",
                        "payments.provider": "stripe",
                    },
                },
            },
        )]

    raw = '{"features": {"authentication": true, "payments": true},' \
          ' "parameters": {"authentication.method": "email_password",' \
          ' "payments.provider": "stripe"}, "roles": ["user"]}'
    baseline = BackendSpecBaseline(completer=_stub_completer(raw), ontology=ontology)
    assert baseline.available()
    for case_name, data in cases():
        result = baseline.run(str(data["input"]), case_name=case_name, ontology=ontology)
        assert not result.skipped
        assert result.spec is not None
        scored = score_baseline(result, extract_labels(data["expected_spec"]), case_name)
        assert scored.metrics is not None
        assert scored.metrics.omissions == 0
        assert scored.metrics.params_match is True


def test_direct_sql_baseline_injected_completer_counts_tables():
    sql = "CREATE TABLE listings (id uuid); CREATE TABLE bookings (id uuid);"
    baseline = DirectSqlBaseline(completer=_stub_completer(sql))
    result = baseline.run("a marketplace with bookings", case_name="c1",
                          gold_entities=["listings", "bookings", "reviews"])
    assert not result.skipped
    assert result.extra == {"tables_found": 2, "gold_tables": 3, "tables_hit": 2}


def test_gemini_completer_absent_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert gemini_completer() is None


def test_gemini_completer_prefers_gemini_key(monkeypatch):
    import tests.experiments.baselines as baselines

    gem, oai, ant = object(), object(), object()
    monkeypatch.setattr(baselines, "gemini_completer", lambda *a, **k: gem)
    monkeypatch.setattr(baselines, "openai_completer", lambda *a, **k: oai)
    monkeypatch.setattr(baselines, "anthropic_completer", lambda *a, **k: ant)
    assert baselines.BackendSpecBaseline()._completer is gem
    assert baselines.DirectSqlBaseline()._completer is gem

    monkeypatch.setattr(baselines, "gemini_completer", lambda *a, **k: None)
    assert baselines.BackendSpecBaseline()._completer is oai
    monkeypatch.setattr(baselines, "openai_completer", lambda *a, **k: None)
    assert baselines.DirectSqlBaseline()._completer is ant
    monkeypatch.setattr(baselines, "anthropic_completer", lambda *a, **k: None)
    assert baselines.BackendSpecBaseline()._completer is None


def test_gemini_completer_posts_to_generate_content_and_parses(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"candidates": [
                {"content": {"parts": [{"text": '{"features": {"bookings": true}}'}]}},
            ]}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResp()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    completer = gemini_completer()
    assert completer is not None
    out = completer.complete("be strict", "a marketplace")
    assert out == '{"features": {"bookings": true}}'
    assert "models/gemini-3.5-flash:generateContent" in captured["url"]
    assert captured["kwargs"]["params"] == {"key": "test-key"}
    assert captured["kwargs"]["json"]["system_instruction"]["parts"][0]["text"] == "be strict"
    assert captured["kwargs"]["json"]["contents"][0]["parts"][0]["text"] == "a marketplace"


def test_gemini_completer_retries_transient_503(monkeypatch):
    import tests.experiments.baselines as baselines

    calls = {"n": 0}

    class FlakyResp:
        def __init__(self) -> None:
            self.status_code = 503 if calls["n"] == 1 else 200
            self.headers = {}

        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        return FlakyResp()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(baselines.random, "random", lambda: 0.0)
    monkeypatch.setattr(httpx, "post", fake_post)
    completer = gemini_completer()
    assert completer is not None
    assert completer.complete("s", "u") == "ok"
    assert calls["n"] == 2


def test_baselines_self_skip_without_credentials(ontology):
    # Runs with no OPENAI_API_KEY / ANTHROPIC_API_KEY: every un-injected
    # adapter must self-skip rather than fail or consume a key.
    baseline = BackendSpecBaseline(ontology=ontology)
    assert not baseline.available()
    result = baseline.run("a marketplace", case_name="c", ontology=ontology)
    assert result.skipped and "credentials" in (result.skip_reason or "")
    direct = DirectSqlBaseline()
    assert not direct.available()

class CompatResp:
    ok_status = 200

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def test_openai_compat_posts_chat_completions_and_parses(monkeypatch):
    calls = {}

    def fake_post(url, **kwargs):
        calls.update(url=url, **kwargs)
        return CompatResp(200, {
            'choices': [{'message': {'content': 'spec json here'}}],
        })

    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gw.example.com/v1beta/openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash')
    monkeypatch.setattr(baselines.httpx, 'post', fake_post)

    completer = baselines.openai_compat_completer()
    assert completer is not None
    out = completer.complete('sys prompt', 'user prompt')

    assert out == 'spec json here'
    assert calls['url'] == 'https://gw.example.com/v1beta/openai/chat/completions'
    assert calls['headers']['Authorization'] == 'Bearer sk-test'
    body = calls['json']
    assert body['model'] == 'gemini-3.5-flash'
    assert body['messages'][0] == {'role': 'system', 'content': 'sys prompt'}
    assert body['messages'][1] == {'role': 'user', 'content': 'user prompt'}


def test_openai_compat_requires_base_url_and_key(monkeypatch):
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert baselines.openai_compat_completer() is None
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gw.example.com/v1')
    assert baselines.openai_compat_completer() is None
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    assert baselines.openai_compat_completer() is not None


def test_openai_compat_retries_transient_then_succeeds(monkeypatch):
    calls = {'n': 0}

    def fake_post(url, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return CompatResp(503, {})
        return CompatResp(200, {'choices': [{'message': {'content': 'ok'}}]})

    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gw.example.com/v1')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    monkeypatch.setattr(baselines.httpx, 'post', fake_post)
    monkeypatch.setattr(baselines.time, 'sleep', lambda s: None)

    completer = baselines.openai_compat_completer()
    assert completer.complete('s', 'u') == 'ok'
    assert calls['n'] == 2


def test_default_completer_prefers_openai_compat(monkeypatch):
    """The compat gateway is tried before the native Gemini REST path, so a
    provided base_url outranks the primary key's daily quota."""
    sentinel = baselines._FnCompleter(lambda s, u: 'compat')

    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gw.example.com/v1')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    monkeypatch.setattr(baselines, 'openai_compat_completer', lambda: sentinel)
    monkeypatch.setattr(baselines, 'gemini_completer', lambda: None)
    from tests.experiments.baselines import default_completer
    assert default_completer() is sentinel
