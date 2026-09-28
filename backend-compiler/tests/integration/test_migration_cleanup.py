# tests/integration/test_migration_cleanup.py
from compiler.deployer.deployer import apply_migrations
from compiler.generator.composer import compose
from compiler.spec.derive import recompute_spec


def test_apply_migrations_clears_stale_files(tmp_path, monkeypatch,
                                              marketplace_spec, ontology):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "compiler.deployer.deployer.subprocess.run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stderr": ""})(),
    )

    migrations_1 = compose(marketplace_spec, ontology)
    assert len(migrations_1) >= 5
    try:
        apply_migrations("ref", "pass", migrations_1)
    except Exception:
        pass

    written_1 = sorted(p.name for p in (tmp_path / "supabase/migrations").iterdir())
    assert len(written_1) == len(migrations_1)

    small_spec = marketplace_spec.model_copy(update={
        "features": {**marketplace_spec.features, "messaging": False},
    })
    small_spec = recompute_spec(small_spec, ontology)
    migrations_2 = compose(small_spec, ontology)
    assert len(migrations_2) < len(migrations_1)

    try:
        apply_migrations("ref", "pass", migrations_2)
    except Exception:
        pass

    written_2 = sorted(p.name for p in (tmp_path / "supabase/migrations").iterdir())
    expected = {m.filename for m in migrations_2}
    assert set(written_2) == expected, \
        f"stale files remain: {set(written_2) - expected}"
