"""Terminal nodes: the conversational reply, and the write-back to Postgres."""

import logging
from datetime import date

from ...database import session_scope
from ...llm import registry, complete
from ...models import Complaint, ComplaintRevision
from ...schemas import ComplaintForm, RiskAssessment
from ..prompts import QMS_CONTEXT
from ..state import ComplaintState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Answer node — the "chat" branch
# ---------------------------------------------------------------------------

ANSWER_SYSTEM = f"""{QMS_CONTEXT}

The user is asking a question rather than supplying complaint data. Answer it
using the complaint record and risk assessment provided. Be direct and brief —
two or three sentences unless the question genuinely needs more. If the record
does not contain the answer, say so and name the field that would need filling.
Never invent complaint data.
"""


def answer_node(state: ComplaintState) -> dict:
    form = state.get("form") or ComplaintForm()
    risk = state.get("risk_assessment") or RiskAssessment()

    context = (
        f"Complaint record:\n{form.model_dump_json(indent=2, exclude_none=True)}\n\n"
        f"Risk assessment:\n{risk.model_dump_json(indent=2, exclude_none=True)}\n\n"
        f"Question: {state.get('user_input', '')}"
    )
    reply = complete(
        system=ANSWER_SYSTEM,
        user=context,
        model=registry.reasoning,
        temperature=0.3,
    ).strip()

    return {
        "assistant_message": reply,
        "updated_fields": [],
        "model_used": registry.reasoning,
        "trace": ["answer_question"],
    }


# ---------------------------------------------------------------------------
# Compose the assistant's confirmation message
# ---------------------------------------------------------------------------

FIELD_LABELS = {
    "complaint_source": "Complaint Source",
    "customer_name": "Customer Name",
    "product_name": "Product Name",
    "product_strength": "Product Strength/Grade",
    "batch_lot_number": "Batch/Lot Number",
    "manufacturing_date": "Manufacturing Date",
    "expiry_date": "Expiry Date",
    "quantity_affected": "Quantity Affected",
    "complaint_type": "Complaint Type",
    "complaint_date": "Complaint Date",
    "detailed_description": "Detailed Description",
    "initial_severity": "Initial Severity",
    "priority": "Priority",
}


def compose_reply_node(state: ComplaintState) -> dict:
    """Build the chat bubble text. Deterministic — no LLM call needed, and it
    guarantees the message can never contradict what actually changed."""
    if state.get("assistant_message"):
        return {"trace": ["compose_reply (already set)"]}

    intent = state.get("intent", "")
    changed = state.get("updated_fields", [])
    risk: RiskAssessment = state.get("risk_assessment") or RiskAssessment()
    completeness = state.get("completeness")
    duplicates = state.get("duplicates")

    if not changed:
        msg = (
            "I could not find any new complaint details in that. Could you tell me "
            "the product, batch number and what the customer observed?"
        )
        return {"assistant_message": msg, "trace": ["compose_reply"]}

    verb = {
        "log_complaint": "Logged the complaint and populated",
        "edit_complaint": "Updated",
        "extract_document": "Extracted the complaint from the document and populated",
    }.get(intent, "Updated")

    labels = [FIELD_LABELS.get(f, f) for f in changed]
    if len(labels) <= 4:
        field_text = ", ".join(labels)
    else:
        field_text = f"{', '.join(labels[:4])} and {len(labels) - 4} more field(s)"

    parts = [f"{verb} {field_text}."]

    if risk.severity_classification:
        parts.append(
            f"Risk assessment: **{risk.severity_classification}** severity"
            + (f" (score {risk.risk_score}/10)" if risk.risk_score else "")
            + "."
        )
    if risk.recommended_next_action:
        parts.append(f"Recommended next action: {risk.recommended_next_action}")

    if duplicates and duplicates.has_duplicates:
        top = duplicates.matches[0]
        parts.append(
            f"⚠ Possible duplicate of {top.complaint_number} ({top.reason}). "
            "Please confirm before saving."
        )

    if completeness and completeness.follow_up_question:
        parts.append(completeness.follow_up_question)

    return {"assistant_message": "\n\n".join(parts), "trace": ["compose_reply"]}


# ---------------------------------------------------------------------------
# Persist node
# ---------------------------------------------------------------------------


def _coerce_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def persist_node(state: ComplaintState) -> dict:
    """Write the merged state back to Postgres and append an audit revision.

    Postgres is the source of truth between turns. The API rehydrates state from
    this table at the start of every request, so a page refresh, a server
    restart or a second browser tab all see the same complaint.
    """
    complaint_id = state.get("complaint_id")
    if not complaint_id:
        return {"trace": ["persist (skipped: no complaint id)"]}

    form: ComplaintForm = state.get("form") or ComplaintForm()
    risk: RiskAssessment = state.get("risk_assessment") or RiskAssessment()
    changed = state.get("updated_fields", [])

    with session_scope() as db:
        row = db.get(Complaint, complaint_id)
        if row is None:
            return {"trace": ["persist (skipped: complaint not found)"]}

        values = form.model_dump()
        for column in Complaint.FORM_COLUMNS:
            value = values.get(column)
            if column in ("manufacturing_date", "expiry_date", "complaint_date"):
                value = _coerce_date(value)
            setattr(row, column, value)

        row.risk_assessment = risk.model_dump(mode="json")
        if state.get("completeness"):
            row.completeness = state["completeness"].model_dump(mode="json")
        if state.get("summary"):
            row.ai_summary = state["summary"]
        if state.get("document_name"):
            row.source_document_name = state["document_name"]
            row.source_document_text = (state.get("document_text") or "")[:20000]

        if row.status == "Draft" and form.filled_fields():
            row.status = "Pending Triage"

        if changed:
            db.add(
                ComplaintRevision(
                    complaint_id=complaint_id,
                    tool_used=state.get("intent", "unknown"),
                    user_input=state.get("user_input"),
                    patch=state.get("patch", {}),
                    changed_fields=changed,
                    model_used=state.get("model_used"),
                )
            )

    logger.info("Persisted complaint %s (%d field(s) changed)", complaint_id, len(changed))
    return {"trace": [f"persist → complaint {complaint_id} saved"]}
