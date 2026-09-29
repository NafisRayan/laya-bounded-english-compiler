"""Edge function scaffolding and deployment (Developer Spec.md §8.7).

Templates live in `compiler/generator/edge_templates/`; only functions
backed by a template are managed (stale managed dirs are removed, unknown
names raise). Deployment shells out to the Supabase CLI per function.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from compiler.deployer.config import supabase_cli
from compiler.spec.models import BackendSpec

__all__ = ["deploy_edge_functions", "scaffold_edge_functions"]

TEMPLATES = Path(__file__).resolve().parent.parent / "generator" / "edge_templates"


def _managed_function_names() -> set[str]:
    return {p.stem for p in TEMPLATES.glob("*.ts")}


def scaffold_edge_functions(spec: BackendSpec) -> None:
    base = Path("supabase/functions")
    if base.exists():
        managed = _managed_function_names()
        for d in base.iterdir():
            if d.is_dir() and d.name in managed:
                shutil.rmtree(d)
    base.mkdir(parents=True, exist_ok=True)

    for fn_name in spec.edge_functions:
        template_src = TEMPLATES / f"{fn_name}.ts"
        if not template_src.exists():
            raise ValueError(f"no template for edge function {fn_name}")
        dest_dir = base / fn_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(template_src, dest_dir / "index.ts")


def deploy_edge_functions(ref: str, spec: BackendSpec) -> None:
    if not spec.edge_functions:
        return
    scaffold_edge_functions(spec)
    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = os.environ.get("SUPABASE_DB_PASSWORD", "")
    for fn_name in spec.edge_functions:
        subprocess.run(
            # --use-api bundles server-side: the default path needs a local
            # Docker toolchain and must reach esm.sh to resolve the
            # supabase-js import, which restricted networks block.
            supabase_cli(
                "functions", "deploy", fn_name, "--project-ref", ref, "--use-api"
            ),
            check=True, capture_output=True, text=True, env=env,
        )
