"""Router node: decides which tool handles this turn.

A deterministic short-circuit runs first. If a document was uploaded there is
nothing to classify, so we skip the LLM call entirely — cheaper, faster and it
removes a class of failure where the model reads the document text and
misroutes to `log_complaint`.
"""

import logging

from ...llm import registry, structured
from ...schemas import RouterDecision
from ..state import ComplaintState

logger = logging.getLogger(__name__)

SYSTEM = """\
You classify a single user message inside a pharmaceutical complaint intake
assistant. Choose exactly one intent.

log_complaint     - The message describes a NEW complaint. Use when the form is
                    currently empty, or when the user is clearly reporting a
                    different product/batch/incident from the one on file.
edit_complaint    - The message corrects, adds to, or amends the complaint
                    already on file. Strong signals: "sorry, the batch number
                    is...", "actually", "change", "update", "it should be",
                    "also", or a bare fact that maps onto a form field while a
                    complaint already exists.
extract_document  - The user is referring to an uploaded document.
answer_question   - The user is asking about the complaint, the process, or the
                    system, and is not supplying new complaint data. Examples:
                    "what's the severity?", "why did you classify it as major?",
                    "what's still missing?"

Bias rule: if a complaint already exists on file and the message supplies facts
rather than asking something, prefer edit_complaint over log_complaint. Wrongly
choosing log_complaint destroys data the user has already entered.
"""


def route_node(state: ComplaintState) -> dict:
    # Deterministic paths first.
    if state.get("has_document"):
        return {
            "intent": "extract_document",
            "intent_reasoning": "A document was uploaded with this turn.",
            "trace": ["router → extract_document (deterministic: document present)"],
        }

    user_input = (state.get("user_input") or "").strip()
    if not user_input:
        return {
            "intent": "answer_question",
            "intent_reasoning": "Empty message.",
            "trace": ["router → answer_question (empty input)"],
        }

    form = state.get("form")
    filled = form.filled_fields() if form else []

    state_line = (
        "NO COMPLAINT ON FILE — the form is completely empty"
        if not filled
        else "A COMPLAINT IS ALREADY ON FILE"
    )
    context = (
        f"Current state: {state_line}\n"
        f"Fields containing data: {', '.join(filled) if filled else 'none'}\n\n"
        f"User message:\n{user_input}"
    )

    decision = structured(
        system=SYSTEM,
        user=context,
        schema=RouterDecision,
        model=registry.reasoning,
    )

    # Safety net: the model cannot pick extract_document without a document.
    intent = decision.intent
    if intent == "extract_document":
        intent = "edit_complaint" if filled else "log_complaint"

    logger.info("Router chose %s (%s)", intent, decision.reasoning)
    return {
        "intent": intent,
        "intent_reasoning": decision.reasoning,
        "model_used": registry.reasoning,
        "trace": [f"router → {intent}"],
    }


def route_edge(state: ComplaintState) -> str:
    """Conditional edge function consumed by `add_conditional_edges`."""
    return state.get("intent", "answer_question")
