# Model Notes

## Summary

The assignment specifies `gemma2-9b-it` on Groq. **That model has been retired
and is not available to new API keys.**

This was found by checking Groq's model list before writing any integration
code, and is handled by resolving models at runtime rather than hard-coding a
substitute.

---

## What happened

| Date | Event |
|---|---|
| 8 Aug 2025 | Groq emailed users announcing the deprecation of `gemma2-9b-it`, recommending `llama-3.1-8b-instant` as the replacement — same speed, better price-performance |
| Oct 2025 | Model removed from production serving |
| Today | Not returned by `GET /openai/v1/models` on a new account |

Sources:
- Groq deprecations page — <https://console.groq.com/docs/deprecations>
- Groq supported models — <https://console.groq.com/docs/models>

The assignment also names `llama-3.3-70b-versatile` ("you may also consider
llama-3.3-70b-versatile for context"), which remains fully supported and is
what this project uses for reasoning.

---

## How the app handles it

Two ordered preference lists in `backend/app/config.py`:

```python
reasoning_model_preference = [
    "llama-3.3-70b-versatile",   # named in the brief, best reasoning
    "openai/gpt-oss-120b",       # fallback if the above is unavailable
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

extraction_model_preference = [
    "gemma2-9b-it",              # the spec model — first choice if it ever returns
    "llama-3.1-8b-instant",      # Groq's own recommended replacement
    "llama-3.3-70b-versatile",
]
```

At startup, `ModelRegistry.resolve()` calls `GET /openai/v1/models`, filters to
active models, and picks the first surviving entry from each list. If
`gemma2-9b-it` is absent it logs a warning naming what it used instead.

Three properties of this approach:

1. **Nothing is hidden.** The substitution is logged at startup and exposed at
   `GET /api/health`, so a reviewer can see exactly which models ran.
2. **The spec is honoured if possible.** `gemma2-9b-it` sits at the head of the
   extraction list. If Groq restores it, the app picks it up with no code change.
3. **It survives the next deprecation.** Groq retires models regularly. A
   hard-coded string breaks silently at 3am; a preference list degrades.

Check what resolved:

```bash
curl localhost:8000/api/health | jq .models
```

```json
{
  "reasoning": "llama-3.3-70b-versatile",
  "extraction": "llama-3.1-8b-instant",
  "spec_model_available": false,
  "live_model_count": 18
}
```

---

## Why two models

Extraction and reasoning are different jobs with different cost profiles.

**Extraction** (`log_complaint`, `edit_complaint`, `extract_document`) is
essentially structured transcription — read text, emit JSON matching a schema.
It doesn't need a frontier model, and it's on the critical path for perceived
latency because nothing renders until it returns. The fast 8B model is the
right fit.

**Reasoning** (`assess_risk`, `answer_question`) is genuine judgement — weigh a
defect against GMP severity tiers, propose root causes specific to a dosage
form, decide whether something is regulatory-reportable. Quality matters more
than latency here, and it runs after the form has already painted, so the extra
second is invisible.

Roughly: 70B where thinking happens, 8B where transcription happens.

---

## Why JSON mode instead of `with_structured_output()`

LangChain's `with_structured_output()` defaults to native function-calling,
which not every Groq model supports — Gemma being the obvious example. Since
the model is resolved at runtime and may be any of five candidates, binding to
a capability only some of them have would make the graph fragile.

`app/llm.py` instead uses:

```python
response_format={"type": "json_object"}
```

with the Pydantic JSON Schema injected into the system prompt, then validates
the reply with `schema.model_validate()`.

JSON mode guarantees *syntactically* valid JSON, not JSON matching our shape.
So when validation fails, the error is sent back to the model and it's asked to
repair its own output — up to `llm_max_retries` times. If it still fails, an
empty schema instance is returned and the graph degrades rather than crashing.
The user loses that turn's extraction, not their form data.

This costs one extra round-trip in the rare failure case and buys portability
across every model in the preference list.

---

## If you want to force a specific model

Edit `backend/app/config.py`, or override per-environment:

```ini
# backend/.env
REASONING_MODEL_PREFERENCE=["llama-3.1-8b-instant"]
EXTRACTION_MODEL_PREFERENCE=["llama-3.1-8b-instant"]
```

Useful if you hit free-tier rate limits — the 8B model has a higher
requests-per-minute allowance than the 70B.
