"""Groq LLM access layer.

Two things happen here that are worth explaining in an interview:

1. **Runtime model resolution.** The assignment names `gemma2-9b-it`, which Groq
   has since retired. Instead of silently substituting a model, the app asks
   Groq which models are live and picks the highest-preference survivor. The
   resolution is logged at startup and surfaced in the API response
   (`model_used`) so the behaviour is visible, not hidden.

2. **JSON mode rather than tool binding.** `with_structured_output()` in
   LangChain leans on native function-calling, which not every Groq model
   supports (Gemma being the obvious example). Using
   `response_format={"type": "json_object"}` plus Pydantic validation keeps the
   graph portable across every model in the preference list, and gives us an
   explicit repair loop when the model returns malformed JSON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from groq import Groq
from pydantic import BaseModel, ValidationError

from .config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ModelRegistry:
    """Resolves the configured model preferences against what Groq actually serves."""

    def __init__(self) -> None:
        self._live: List[str] = []
        self._reasoning: Optional[str] = None
        self._extraction: Optional[str] = None
        self._resolved = False

    def _fetch_live_models(self) -> List[str]:
        if not settings.groq_api_key:
            return []
        try:
            resp = httpx.get(
                f"{settings.groq_base_url}/models",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [m["id"] for m in data if m.get("active", True)]
        except Exception as exc:  # noqa: BLE001 - startup must not hard-fail
            logger.warning("Could not list Groq models (%s); using first preference", exc)
            return []

    @staticmethod
    def _pick(preferences: List[str], live: List[str]) -> str:
        for candidate in preferences:
            if candidate in live:
                return candidate
        return preferences[0]

    def resolve(self) -> None:
        self._live = self._fetch_live_models()
        self._reasoning = self._pick(settings.reasoning_model_preference, self._live)
        self._extraction = self._pick(settings.extraction_model_preference, self._live)
        self._resolved = True

        if "gemma2-9b-it" not in self._live and self._live:
            logger.warning(
                "gemma2-9b-it (named in the assignment) is not available on this "
                "Groq account. Falling back to extraction=%s, reasoning=%s. "
                "See docs/MODEL_NOTES.md.",
                self._extraction,
                self._reasoning,
            )
        logger.info(
            "Model resolution complete: reasoning=%s extraction=%s (%d live models)",
            self._reasoning,
            self._extraction,
            len(self._live),
        )

    @property
    def reasoning(self) -> str:
        if not self._resolved:
            self.resolve()
        return self._reasoning or settings.reasoning_model_preference[0]

    @property
    def extraction(self) -> str:
        if not self._resolved:
            self.resolve()
        return self._extraction or settings.extraction_model_preference[0]

    @property
    def live_models(self) -> List[str]:
        if not self._resolved:
            self.resolve()
        return self._live


registry = ModelRegistry()
_client: Optional[Groq] = None


def get_client() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
                "and add a key from https://console.groq.com/keys"
            )
        _client = Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds)
    return _client


def _extract_json(raw: str) -> str:
    """Pull a JSON object out of a response that may be fenced or prefixed."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw


def complete(
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """Plain text completion."""
    client = get_client()
    resp = client.chat.completions.create(
        model=model or registry.reasoning,
        temperature=settings.llm_temperature if temperature is None else temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def structured(
    system: str,
    user: str,
    schema: Type[T],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> T:
    """Call the LLM and validate the reply against a Pydantic schema.

    The JSON schema is injected into the system prompt because JSON mode
    guarantees *syntactically* valid JSON, not JSON matching our shape. On a
    validation failure we send the error back to the model once and let it
    repair its own output before giving up.
    """
    client = get_client()
    chosen = model or registry.reasoning
    schema_json = json.dumps(schema.model_json_schema(), indent=2)

    system_prompt = (
        f"{system}\n\n"
        "Respond with a single JSON object and nothing else. No prose, no "
        "markdown fences, no explanation outside the JSON.\n\n"
        f"The object must validate against this JSON Schema:\n{schema_json}\n\n"
        "Omit any field you are not confident about rather than guessing or "
        "inventing a placeholder. Omitted fields are treated as 'unchanged', "
        "which is the desired behaviour when information is absent."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]

    last_error: Optional[Exception] = None
    for attempt in range(settings.llm_max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=chosen,
                temperature=settings.llm_temperature if temperature is None else temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
            raw = resp.choices[0].message.content or "{}"
            payload = json.loads(_extract_json(raw))
            return schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning("Structured call attempt %d failed: %s", attempt + 1, exc)
            messages.append({"role": "assistant", "content": raw if "raw" in dir() else "{}"})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That output was rejected by the validator:\n{exc}\n\n"
                        "Return corrected JSON that satisfies the schema. JSON only."
                    ),
                }
            )

    logger.error("Structured call exhausted retries: %s", last_error)
    return schema()  # empty instance: the graph degrades rather than crashes
