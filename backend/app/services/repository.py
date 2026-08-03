"""Repository layer: the bridge between SQLAlchemy rows and graph state.

Keeping this separate from the router means the graph never imports FastAPI and
the API never touches the ORM directly — each layer is testable on its own.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import ChatTurn, Complaint
from ..schemas import (
    ComplaintForm,
    CompletenessReport,
    DuplicateReport,
    RiskAssessment,
)


def create_complaint(db: Session) -> Complaint:
    """Open a blank complaint with a collision-proof complaint number.

    The number is derived from the row's own primary key rather than from a
    COUNT(*). Counting is wrong twice over: two concurrent requests both read
    the same count and generate the same number (React StrictMode double-mounts
    in dev, so this fires on every page load), and deleting a row makes the
    next count collide with an existing number.

    Deriving from the sequence-assigned id is race-free by construction. We
    flush to obtain the id, then set the human-readable number in the same
    transaction.
    """
    row = Complaint(
        complaint_number=f"PENDING-{uuid4().hex[:12]}",  # placeholder, satisfies NOT NULL + UNIQUE
        status="Draft",
        risk_assessment={},
        completeness={},
    )
    db.add(row)
    db.flush()  # assigns row.id from the Postgres sequence

    row.complaint_number = f"CC-{datetime.now().year}-{row.id:04d}"
    db.commit()
    db.refresh(row)
    return row


def get_complaint(db: Session, complaint_id: int) -> Optional[Complaint]:
    return db.get(Complaint, complaint_id)


def row_to_form(row: Complaint) -> ComplaintForm:
    """Rehydrate the form from the typed columns.

    Nones are filtered out rather than passed through, so a column that was
    never populated stays 'unset' on the model. That keeps `merge()`'s
    exclude_unset semantics correct across a round-trip through the database.
    """
    data = {c: getattr(row, c) for c in Complaint.FORM_COLUMNS}
    return ComplaintForm.model_validate({k: v for k, v in data.items() if v is not None})


def row_to_risk(row: Complaint) -> RiskAssessment:
    try:
        return RiskAssessment.model_validate(row.risk_assessment or {})
    except Exception:  # noqa: BLE001
        return RiskAssessment()


def row_to_completeness(row: Complaint) -> CompletenessReport:
    try:
        return CompletenessReport.model_validate(row.completeness or {})
    except Exception:  # noqa: BLE001
        return CompletenessReport()


def build_initial_state(row: Complaint, user_input: str = "", document_text: str | None = None,
                        document_name: str | None = None) -> dict:
    """Assemble the graph's entry state from the database row plus this turn's input."""
    return {
        "complaint_id": row.id,
        "complaint_number": row.complaint_number,
        "user_input": user_input,
        "document_text": document_text,
        "document_name": document_name,
        "has_document": bool(document_text),
        "form": row_to_form(row),
        "risk_assessment": row_to_risk(row),
        "completeness": row_to_completeness(row),
        "duplicates": DuplicateReport(),
        "summary": row.ai_summary,
        "updated_fields": [],
        "assistant_message": "",
        "trace": [],
    }


def log_turn(db: Session, complaint_id: int, role: str, content: str,
             tool_used: str | None = None) -> None:
    db.add(ChatTurn(complaint_id=complaint_id, role=role, content=content, tool_used=tool_used))
    db.commit()


def reset_complaint(db: Session, row: Complaint) -> Complaint:
    """Clear the form back to Draft. Revisions are intentionally NOT deleted —
    the audit trail survives a reset."""
    for column in Complaint.FORM_COLUMNS:
        setattr(row, column, None)
    row.risk_assessment = {}
    row.completeness = {}
    row.ai_summary = None
    row.source_document_name = None
    row.source_document_text = None
    row.status = "Draft"
    db.commit()
    db.refresh(row)
    return row