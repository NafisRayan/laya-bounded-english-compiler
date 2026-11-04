# LLM-annotator run manifest (disclosed)

- Date: 2026-11-04
- Annotator: LLM (disclosed; not human) via `_FnCompleter`
- Model: `{'OPENAI_MODEL': 'antigravity/gemini-3.8-flash-tiered', 'GEMINI_MODEL': 'gemini-3.5-flash'}`
- Instructions: `tests/annotation/external/README-annotator.md` (sha256[:16] `973acedab7be111d`, identical text as issued to human annotators)
- Cases: 50 (0 failures)

This is a sensitivity datapoint against author bias in the gold,
NOT a substitute for independent human annotation. The paper must
label it exactly as an LLM annotator. Score with:

    python -m tests.annotation.cohen_kappa --annotator2 tests/annotation/llm_annotator
