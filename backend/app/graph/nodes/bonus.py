"""Bonus feature nodes.

Three of the optional features from the brief, chosen because each one uses a
different mechanism rather than being three variations on "ask the LLM":

- completeness_node   : deterministic rule check + one LLM call for phrasing
- duplicate_node      : pure SQL against Postgres, no LLM at all
- summary_node        : single LLM call producing a QA-reviewer-facing digest

Root Cause Recommendation and CAPA Recommendation are also implemented, but as
fields on the risk assessment rather than separate nodes, since they are drawn
from the same reasoning pass over the same record.
"""

import logging
from typing import List

from sqlalchemy import or_, select

from ...database import session_scope
from ...llm import registry, complete, structured
from ...models import Complaint
from ...schemas import (
    ComplaintForm,
    CompletenessReport,
    DuplicateMatch,
    DuplicateReport,
)
from ..state import ComplaintState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Completeness checker
# ---------------------------------------------------------------------------

# Mandatory under a typical complaint-handling SOP: you cannot open an
# investigation without knowing what product, which batch, who reported it and
# what went wrong.
MANDATORY_FIELDS = [
    "customer_name",
    "product_name",
    "batch_lot_number",
    "complaint_type",
    "detailed_description",
    "quantity_affected",
    "complaint_date",
]

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
    "detailed_description": "Detailed Complaint Description",
    "initial_severity": "Initial Severity",
    "priority": "Priority",
}


def completeness_node(state: ComplaintState) -> dict:
    """Deterministic gap analysis, with the LLM used only to phrase the ask."""
    form: ComplaintForm = state.get("form") or ComplaintForm()
    values = form.model_dump()

    missing = [f for f in MANDATORY_FIELDS if values.get(f) in (None, "")]
    filled_count = len([v for v in values.values() if v not in (None, "")])
    percent = round(100 * filled_count / len(values))

    report = CompletenessReport(
        is_complete=not missing,
        missing_mandatory_fields=[FIELD_LABELS.get(f, f) for f in missing],
        percent_complete=percent,
    )

    if missing and filled_count:
        # One short LLM call so the follow-up reads naturally instead of
        # "Please provide: batch_lot_number, quantity_affected".
        report.follow_up_question = complete(
            system=(
                "You are a pharmaceutical complaint intake assistant. Write ONE "
                "short, polite sentence asking the user for the missing details "
                "listed. Refer to them by their business names. Address the user "
                "directly as 'you' — do NOT invent or use any name, company or "
                "salutation. No preamble, no bullet points, no more than 25 words."
            ),
            user=f"Missing: {', '.join(report.missing_mandatory_fields)}",
            model=registry.extraction,
            temperature=0.3,
        ).strip()

    return {
        "completeness": report,
        "trace": [f"completeness_check ({percent}% complete, {len(missing)} mandatory gaps)"],
    }


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _similarity(a: str | None, b: str | None) -> float:
    """Cheap token-overlap score. Good enough for product-name matching and it
    keeps the dependency list short."""
    if not a or not b:
        return 0.0
    ta = set(a.lower().replace("/", " ").split())
    tb = set(b.lower().replace("/", " ").split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def duplicate_node(state: ComplaintState) -> dict:
    """Query the complaints table for prior reports on the same batch or product.

    No LLM here. Duplicate detection against structured columns is a database
    problem, and doing it in SQL means it is exact, instant and free.
    """
    form: ComplaintForm = state.get("form") or ComplaintForm()
    if not form.batch_lot_number and not form.product_name:
        return {"duplicates": DuplicateReport(), "trace": ["duplicate_check (skipped: no identifiers)"]}

    current_id = state.get("complaint_id", -1)
    matches: List[DuplicateMatch] = []

    with session_scope() as db:
        stmt = select(Complaint).where(Complaint.id != current_id)
        clauses = []
        if form.batch_lot_number:
            clauses.append(Complaint.batch_lot_number == form.batch_lot_number)
        if form.product_name:
            clauses.append(Complaint.product_name.ilike(f"%{form.product_name.split()[0]}%"))
        stmt = stmt.where(or_(*clauses)).order_by(Complaint.id.desc()).limit(25)

        for row in db.execute(stmt).scalars():
            score = 0
            reasons = []

            if form.batch_lot_number and row.batch_lot_number == form.batch_lot_number:
                score += 60
                reasons.append("identical batch/lot number")

            name_sim = _similarity(form.product_name, row.product_name)
            if name_sim > 0.5:
                score += int(30 * name_sim)
                reasons.append("same product")

            if form.customer_name and row.customer_name:
                if _similarity(form.customer_name, row.customer_name) > 0.5:
                    score += 15
                    reasons.append("same customer")

            if form.complaint_type and row.complaint_type == form.complaint_type:
                score += 10
                reasons.append("same complaint type")

            if score >= 55:
                matches.append(
                    DuplicateMatch(
                        complaint_id=row.id,
                        complaint_number=row.complaint_number,
                        product_name=row.product_name,
                        batch_lot_number=row.batch_lot_number,
                        similarity=min(score, 100),
                        reason=", ".join(reasons),
                    )
                )

    matches.sort(key=lambda m: m.similarity, reverse=True)
    report = DuplicateReport(has_duplicates=bool(matches), matches=matches[:3])
    return {
        "duplicates": report,
        "trace": [f"duplicate_check ({len(matches)} potential duplicate(s))"],
    }


# ---------------------------------------------------------------------------
# Complaint summary
# ---------------------------------------------------------------------------


def summary_node(state: ComplaintState) -> dict:
    """A two-sentence digest for the QA reviewer's worklist."""
    form: ComplaintForm = state.get("form") or ComplaintForm()
    if not state.get("updated_fields") or not form.product_name:
        return {"trace": ["summary (skipped)"]}

    text = complete(
        system=(
            "Summarise this pharmaceutical customer complaint in exactly two "
            "sentences for a QA reviewer's worklist. Sentence one: who reported "
            "what defect, on which product and batch. Sentence two: the scale of "
            "the issue and the assessed severity. Plain factual register, no "
            "preamble, no bullet points."
        ),
        user=form.model_dump_json(indent=2, exclude_none=True),
        model=registry.extraction,
        temperature=0.2,
    ).strip()

    return {"summary": text, "trace": ["summary generated"]}
