"""Baseline adapters (Developer Spec.md §4.2), credential-gated.

Baselines that need an external model/tool self-skip when their credentials
are absent, mirroring the e2e tier. The two LLM baselines accept an injected
``complete(system, user) -> str`` so the parse -> BackendSpec -> score path
is fully testable offline; the real completers (OpenAI / Anthropic) are only
constructed when the corresponding env key is set.

Baselines:
  1. End-to-end LLM direct-to-SQL  (artifact-level: table-presence scoring).
  2. LLM -> BackendSpec JSON -> the SAME fragment composer (isolates the IR).
  3. Rules-only / Laya-only  -> the ablation runner ('AB' / 'C'), already
     measured on the golden corpus (see run_ablation.py).
  4. DbSmash / off-the-shelf Supabase generator  -> external tool surface.

Every run records the raw model output so failures are auditable.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any, Callable, Protocol, Sequence

import httpx

from compiler.ontology.loader import Ontology
from compiler.spec.derive import recompute_spec
from compiler.spec.models import BackendSpec
from tests.experiments.metrics import CaseLabels, RunMetrics, score

__all__ = [
    "BACKEND_SPEC_SYSTEM_PROMPT",
    "DIRECT_SQL_SYSTEM_PROMPT",
    "BaselineResult",
    "BackendSpecBaseline",
    "DbSmashBaseline",
    "DirectSqlBaseline",
    "anthropic_completer",
    "backend_spec_prompt",
    "default_completer",
    "gemini_completer",
    "openai_compat_completer",
    "openai_completer",
    "parse_backend_spec",
    "table_names_from_sql",
]

BACKEND_SPEC_SYSTEM_PROMPT = Template("""\
You are compiling a natural-language backend description into the BackendSpec \
intermediate representation. Output ONE JSON object with exactly these keys: \
version ("1.0"), ontology_version (1), features (a dict of feature id -> \
bool), parameters (a dict of "feature.parameter" -> value), roles (a list of \
role ids), rls_overrides ({}), entities (list of entity ids), buckets (list \
of {name, public, rls_pattern, file_size_limit_mb}), edge_functions (list of \
names), decisions ([]), defaulted ([]), unsupported ([]).

Allowed feature ids: $features
Allowed entity ids: $entities
Allowed roles: $roles
Parameter choices: $param_choices

Only enable a feature if the description supports it; only include entities \
that the text talks about. Emit nothing but the JSON.\
""")

DIRECT_SQL_SYSTEM_PROMPT = """\
You are generating a Supabase SQL migration for a backend described in \
natural language. Emit only SQL: CREATE TABLE statements, ADD FOREIGN KEY, \
and RLS policies. Do not write commentary.\
"""


class LlmCompleter(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's completion for a system/user prompt pair."""


class _FnCompleter:
    """Expose a plain (system, user) -> str function as an LlmCompleter."""

    def __init__(self, fn: Callable[[str, str], str]) -> None:
        self._fn = fn

    def complete(self, system: str, user: str) -> str:
        return self._fn(system, user)


def openai_completer(model: str = "gpt-4o") -> LlmCompleter | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    url = "https://api.openai.com/v1/chat/completions"

    def complete(system: str, user: str) -> str:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return _FnCompleter(complete)


def openai_compat_completer(model: str | None = None) -> LlmCompleter | None:
    """Completer for ANY OpenAI-compatible gateway (OpenRouter, proxy
    gateways, Gemini's own ``/v1beta/openai`` shim, vLLM, ...).

    Gated on ``OPENAI_BASE_URL`` + ``OPENAI_API_KEY``; the model defaults to
    ``OPENAI_MODEL``, then ``GEMINI_MODEL`` (the common case: serving a
    Gemini model through a compatible endpoint), then ``gemini-2.5-flash``.
    The base URL follows the OpenAI SDK convention: it is the full prefix,
    so ``{base}/chat/completions`` is the endpoint. Retries transient
    failures (429 / 5xx / 408) like :func:`gemini_completer`.
    """
    base = os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("OPENAI_API_KEY")
    if not base or not key:
        return None
    model = model or os.environ.get("OPENAI_MODEL") or os.environ.get("GEMINI_MODEL") \
        or "gemini-2.5-flash"
    url = base.rstrip("/") + "/chat/completions"

    def complete(system: str, user: str) -> str:
        body = {"model": model, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]}
        retry_after_s = [10.0, 30.0, 60.0, 120.0]
        delay_s = [2.0, 4.0, 8.0, 16.0]
        last: Exception | None = None
        for attempt in range(4):
            try:
                resp = httpx.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json=body, timeout=120.0,
                )
                if resp.status_code in (408, 429, 500, 502, 503, 504):
                    wait = retry_after_s[attempt] if resp.status_code == 429 \
                        else delay_s[attempt]
                    header = resp.headers.get("Retry-After")
                    if header and header.isdigit():
                        wait = max(wait, float(header))
                    time.sleep(wait + random.random())
                    last = RuntimeError(f"HTTP {resp.status_code}")
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPError as exc:
                time.sleep(delay_s[attempt] + random.random())
                last = exc
        raise RuntimeError(f"OpenAI-compatible call failed after retries: {last}")

    return _FnCompleter(complete)


def default_completer() -> LlmCompleter | None:
    """Precedence for an LLM completer: an OpenAI-compatible gateway first
    (a provided base_url exists precisely to bypass a primary key's quota),
    then the native Gemini REST path, then OpenAI, then Anthropic."""
    return (openai_compat_completer() or gemini_completer()
            or openai_completer() or anthropic_completer())


def anthropic_completer(model: str = "claude-sonnet-4-20250514") -> LlmCompleter | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    url = "https://api.anthropic.com/v1/messages"

    def complete(system: str, user: str) -> str:
        resp = httpx.post(
            url,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            json={"model": model, "max_tokens": 4000,
                  "system": system, "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}]},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    return _FnCompleter(complete)


def gemini_completer(model: str | None = None) -> LlmCompleter | None:
    """Google Gemini completer via the REST generateContent endpoint.

    Gated on ``GEMINI_API_KEY`` (falls back to ``GOOGLE_API_KEY``); model
    defaults to ``gemini-3.5-flash`` (override with ``GEMINI_MODEL``). Uses
    the public REST API so no SDK dependency is needed. Retries transient
    failures (429 / 5xx / network) with backoff; ``Retry-After`` (when
    present) overrides the 429 wait, which otherwise grows per attempt.
    A fixed inter-request pause can be set with ``GEMINI_PACING_MS``.
    """
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    model = model or os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def complete(system: str, user: str) -> str:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
        }
        kwargs: dict[str, Any] = {"params": {"key": key}, "json": body, "timeout": 120.0}
        pacing_s = int(os.environ.get("GEMINI_PACING_MS", "0")) / 1000.0
        retry_after_s = [10.0, 30.0, 60.0, 120.0]
        delay_s = [2.0, 4.0, 8.0, 16.0]
        last: Exception | None = None
        for attempt in range(4):
            if pacing_s and attempt == 0:
                time.sleep(pacing_s)
            try:
                resp = httpx.post(url, **kwargs)
                if resp.status_code in (408, 429, 500, 502, 503, 504):
                    wait = retry_after_s[attempt] if resp.status_code == 429 else delay_s[attempt]
                    header = resp.headers.get("Retry-After")
                    if header and header.isdigit():
                        wait = max(wait, float(header))
                    time.sleep(wait + random.random())
                    last = RuntimeError(f"HTTP {resp.status_code}")
                    continue
                resp.raise_for_status()
                parts = resp.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts)
            except httpx.HTTPError as exc:
                time.sleep(delay_s[attempt] + random.random())
                last = exc
        raise RuntimeError(f"Gemini call failed after retries: {last}")

    return _FnCompleter(complete)


@dataclass
class BaselineResult:
    baseline: str
    case: str
    skipped: bool
    skip_reason: str | None = None
    metrics: RunMetrics | None = None
    extra: dict[str, int] = field(default_factory=dict)
    raw_output: str = ""
    spec: BackendSpec | None = None


def score_baseline(result: BaselineResult, labels: CaseLabels,
                   case_name: str) -> BaselineResult:
    """Attach fidelity metrics to a baseline run against the case's labels."""
    if result.spec is not None:
        result.metrics = score(result.spec, labels, case=case_name,
                               mechanisms=result.baseline, mcq=False)
    return result


def _vocabulary(ontology: Ontology) -> dict[str, str]:
    param_choices = {
        f"{fid}.{pid}": ",".join(p.options) if p.options else p.type
        for fid, fdef in ontology.features.items()
        for pid, p in fdef.parameters.items()
    }
    return {
        "features": ", ".join(sorted(ontology.features)),
        "entities": ", ".join(sorted(ontology.entities)),
        "roles": ", ".join(sorted(ontology.roles)),
        "param_choices": "; ".join(f"{k} in {{{v}}}" for k, v in sorted(param_choices.items())),
    }


def backend_spec_prompt(input_text: str, ontology: Ontology) -> str:
    """The one-shot user prompt for the BackendSpec-isolating baseline."""
    return f"Backend description:\n{input_text}\n\nEmit the BackendSpec JSON."


def parse_backend_spec(text: str, ontology: Ontology,
                       case_name: str = "") -> BackendSpec | None:
    """Extract a BackendSpec from model output; returns None on parse failure.

    Tolerates fenced JSON and leading prose; fills required bookkeeping
    fields (decisions/defaulted/unsupported) with empty lists.
    """
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("version", "1.0")
    data.setdefault("ontology_version", ontology.version)
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    data.setdefault("rls_overrides", {})
    data.setdefault("entities", [])
    data.setdefault("buckets", [])
    data.setdefault("edge_functions", [])
    data.setdefault("decisions", [])
    data.setdefault("defaulted", [])
    data.setdefault("unsupported", [])
    data["features"] = data.get("features") or {}
    data["parameters"] = data.get("parameters") or {}
    data["roles"] = data.get("roles") or []
    try:
        spec = BackendSpec.model_validate(data)
    except Exception:
        return None
    try:
        return recompute_spec(spec, ontology)
    except Exception:
        return spec


def table_names_from_sql(sql: str) -> list[str]:
    """CREATE TABLE names in generated SQL (artifact-level baseline scoring)."""
    names = []
    for m in re.finditer(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(?:\"|`)?([A-Za-z_][A-Za-z0-9_]*)(?:\"|`)?",
        sql, re.IGNORECASE | re.DOTALL):
        name = m.group(1)
        if name not in names:
            names.append(name)
    return names


class BackendSpecBaseline:
    """Baseline 2: LLM -> BackendSpec JSON -> same composer (isolates the IR).

    Unless a completer is injected (offline tests / fixtures), construction
    fails-fast with a null completer that self-reports as unavailable.
    """

    name = "llm_backend_spec"

    def __init__(self, completer: LlmCompleter | None = None,
                 ontology: Ontology | None = None):
        if completer is None:
            self._completer = default_completer()
        else:
            self._completer = completer
        self._ontology: Ontology | None = ontology

    def available(self) -> bool:
        return self._completer is not None and self._ontology is not None

    def run(self, input_text: str, case_name: str = "",
            ontology: Ontology | None = None) -> BaselineResult:
        if not self.available():
            return BaselineResult(
                baseline=self.name, case=case_name, skipped=True,
            skip_reason=("no LLM credentials "
                         "(OPENAI_BASE_URL+OPENAI_API_KEY / GEMINI_API_KEY / "
                         "OPENAI_API_KEY / ANTHROPIC_API_KEY)"),
            )
        ont = ontology or self._ontology
        assert ont is not None and self._completer is not None
        system = BACKEND_SPEC_SYSTEM_PROMPT.substitute(**_vocabulary(ont))
        try:
            raw = self._completer.complete(system, backend_spec_prompt(input_text, ont))
        except Exception as exc:  # network / vendor error -> skip, keep raw
            return BaselineResult(baseline=self.name, case=case_name,
                                  skipped=True, skip_reason=f"LLM call failed: {exc}")
        spec = parse_backend_spec(raw, ont, case_name=case_name)
        return BaselineResult(
            baseline=self.name, case=case_name, skipped=False,
            metrics=None, raw_output=raw, spec=spec,
        )


class DirectSqlBaseline:
    """Baseline 1: end-to-end LLM direct-to-SQL.

    Artifact-level scoring: the gold set pins entity lists per case; we
    report how many gold entity tables appear as CREATE TABLE in the output.
    """

    name = "llm_direct_sql"

    def __init__(self, completer: LlmCompleter | None = None):
        if completer is None:
            self._completer = default_completer()
        else:
            self._completer = completer

    def available(self) -> bool:
        return self._completer is not None

    def run(self, input_text: str, case_name: str = "",
            gold_entities: Sequence[str] | None = None) -> BaselineResult:
        if not self.available():
            return BaselineResult(
                baseline=self.name, case=case_name, skipped=True,
            skip_reason=("no LLM credentials "
                         "(OPENAI_BASE_URL+OPENAI_API_KEY / GEMINI_API_KEY / "
                         "OPENAI_API_KEY / ANTHROPIC_API_KEY)"),
            )
        assert self._completer is not None
        try:
            raw = self._completer.complete(DIRECT_SQL_SYSTEM_PROMPT, input_text)
        except Exception as exc:
            return BaselineResult(baseline=self.name, case=case_name,
                                  skipped=True, skip_reason=f"LLM call failed: {exc}")
        tables = set(table_names_from_sql(raw))
        gold = set(gold_entities or [])
        return BaselineResult(
            baseline=self.name, case=case_name, skipped=False,
            extra={"tables_found": len(tables), "gold_tables": len(gold),
                   "tables_hit": len(tables & gold)},
            raw_output=raw,
        )


class DbSmashBaseline:
    """Baseline 5: off-the-shelf generator CLI (npm ``dbsmash``).

    Discovered contract (dbsmash 1.0.7): the app description goes in on
    stdin, the tool scaffolds into its CWD, and generation shells out to
    OpenRouter, so ``OPENROUTER_API_KEY`` must be in the environment.
    Scoring is artifact-level like :class:`DirectSqlBaseline`: every
    CREATE TABLE in the scaffolded ``*.sql`` counts, and we report gold
    hits. ``DBSMASH_CMD`` overrides the executable; otherwise the CLI is
    resolved from PATH (npm installs a Windows shim, which is routed
    through ``cmd`` — same treatment as the Supabase CLI in
    :mod:`compiler.deployer.config`).
    """

    name = "dbsmash"

    @staticmethod
    def _cmd() -> list[str] | None:
        override = os.environ.get("DBSMASH_CMD")
        if override:
            return [override]
        exe = shutil.which("dbsmash.exe") or shutil.which("dbsmash")
        if exe is None:
            return None
        if os.name == "nt" and not exe.lower().endswith(".exe"):
            return ["cmd", "/c", exe]
        return [exe]

    def available(self) -> bool:
        return self._cmd() is not None and bool(os.environ.get("OPENROUTER_API_KEY"))

    def run(self, input_text: str, case_name: str = "",
            gold_entities: Sequence[str] | None = None) -> BaselineResult:
        cmd = self._cmd()
        missing = []
        if cmd is None:
            missing.append("the dbsmash CLI on PATH (npm install -g dbsmash)")
        if not os.environ.get("OPENROUTER_API_KEY"):
            missing.append("OPENROUTER_API_KEY (the tool calls OpenRouter)")
        if missing:
            return BaselineResult(
                baseline=self.name, case=case_name, skipped=True,
                skip_reason="; ".join(missing),
            )

        env = os.environ.copy()
        with tempfile.TemporaryDirectory(prefix="dbsmash-") as tmp:
            try:
                completed = subprocess.run(
                    cmd,
                    input=input_text, cwd=tmp, env=env,
                    capture_output=True, text=True, timeout=600,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return BaselineResult(baseline=self.name, case=case_name,
                                      skipped=True, skip_reason=f"dbsmash failed: {exc}")
            if completed.returncode != 0:
                return BaselineResult(
                    baseline=self.name, case=case_name, skipped=True,
                    skip_reason=f"dbsmash exited {completed.returncode}: "
                                f"{(completed.stderr or '')[-300:]}",
                )
            sql_files = sorted(Path(tmp).rglob("*.sql"))
            raw = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                            for p in sql_files)

        tables = set(table_names_from_sql(raw))
        gold = set(gold_entities or [])
        return BaselineResult(
            baseline=self.name, case=case_name, skipped=False,
            extra={"tables_found": len(tables), "gold_tables": len(gold),
                   "tables_hit": len(tables & gold)},
            raw_output=raw,
        )


def all_baselines(ontology: Ontology) -> list[Any]:
    return [
        BackendSpecBaseline(ontology=ontology),
        DirectSqlBaseline(),
        DbSmashBaseline(),
    ]