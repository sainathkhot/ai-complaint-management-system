"""Complaint API.

The important endpoint is `POST /api/complaints/{id}/message`. It is a single
multipart endpoint that accepts an optional text message and an optional file,
because from the graph's point of view they are the same event: "the user did
something, run the workflow". Splitting them into /chat and /upload would push
the routing decision into the frontend, where it does not belong.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..graph.builder import get_graph
from ..llm import registry
from ..models import Complaint, ComplaintRevision
from ..schemas import (
    ChatMessage,
    ComplaintListItem,
    ComplaintStateResponse,
    ComplaintStatus,
    DuplicateReport,
)
from ..services import repository as repo
from ..services.document import UnsupportedDocument, extract_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def _to_response(row: Complaint, result: dict) -> ComplaintStateResponse:
    return ComplaintStateResponse(
        complaint_id=row.id,
        complaint_number=row.complaint_number,
        status=ComplaintStatus(row.status),
        form=result["form"],
        risk_assessment=result.get("risk_assessment") or repo.row_to_risk(row),
        completeness=result.get("completeness") or repo.row_to_completeness(row),
        duplicates=result.get("duplicates") or DuplicateReport(),
        summary=result.get("summary"),
        assistant_message=result.get("assistant_message", ""),
        tool_used=result.get("intent"),
        trace=result.get("trace", []),
        model_used=result.get("model_used"),
        updated_fields=result.get("updated_fields", []),
    )


@router.post("", response_model=ComplaintStateResponse, status_code=201)
def create_complaint(db: Session = Depends(get_db)):
    """Open a blank complaint. The frontend calls this once on load."""
    row = repo.create_complaint(db)
    return ComplaintStateResponse(
        complaint_id=row.id,
        complaint_number=row.complaint_number,
        status=ComplaintStatus.DRAFT,
        form=repo.row_to_form(row),
        risk_assessment=repo.row_to_risk(row),
        completeness=repo.row_to_completeness(row),
        duplicates=DuplicateReport(),
        assistant_message=(
            "Upload a complaint document or describe the complaint below. "
            "I'll extract the details and populate the form for you."
        ),
    )


@router.get("", response_model=List[ComplaintListItem])
def list_complaints(db: Session = Depends(get_db), limit: int = 50):
    rows = db.execute(
        select(Complaint).order_by(Complaint.id.desc()).limit(limit)
    ).scalars().all()
    return [
        ComplaintListItem(
            complaint_id=r.id,
            complaint_number=r.complaint_number,
            product_name=r.product_name,
            batch_lot_number=r.batch_lot_number,
            customer_name=r.customer_name,
            initial_severity=r.initial_severity,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{complaint_id}", response_model=ComplaintStateResponse)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    row = repo.get_complaint(db, complaint_id)
    if row is None:
        raise HTTPException(404, "Complaint not found")
    return ComplaintStateResponse(
        complaint_id=row.id,
        complaint_number=row.complaint_number,
        status=ComplaintStatus(row.status),
        form=repo.row_to_form(row),
        risk_assessment=repo.row_to_risk(row),
        completeness=repo.row_to_completeness(row),
        duplicates=DuplicateReport(),
        summary=row.ai_summary,
        assistant_message="",
    )


@router.get("/{complaint_id}/messages", response_model=List[ChatMessage])
def get_messages(complaint_id: int, db: Session = Depends(get_db)):
    row = repo.get_complaint(db, complaint_id)
    if row is None:
        raise HTTPException(404, "Complaint not found")
    return [
        ChatMessage(role=m.role, content=m.content, tool_used=m.tool_used)
        for m in row.messages
    ]


@router.post("/{complaint_id}/message", response_model=ComplaintStateResponse)
async def send_message(
    complaint_id: int,
    message: Optional[str] = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
):
    """The one endpoint that drives everything.

    Flow: load row → hydrate state → invoke graph → graph persists → respond.
    The thread_id passed to the checkpointer is the complaint id, so LangGraph
    keeps per-complaint history isolated.
    """
    row = repo.get_complaint(db, complaint_id)
    if row is None:
        raise HTTPException(404, "Complaint not found")

    document_text = None
    document_name = None

    if file is not None and file.filename:
        data = await file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                413, f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit"
            )
        try:
            document_text = extract_text(file.filename, data)
        except UnsupportedDocument as exc:
            raise HTTPException(400, str(exc)) from exc
        document_name = file.filename
        if not document_text.strip():
            raise HTTPException(
                400,
                "No text layer found in that file. If it is a scanned image, "
                "paste the complaint text instead.",
            )

    if not message and not document_text:
        raise HTTPException(400, "Send a message or attach a document")

    state = repo.build_initial_state(row, message or "", document_text, document_name)

    try:
        result = get_graph().invoke(
            state, config={"configurable": {"thread_id": f"complaint-{complaint_id}"}}
        )
    except RuntimeError as exc:  # missing API key and similar setup errors
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Graph invocation failed")
        raise HTTPException(500, f"The assistant could not process that: {exc}") from exc

    db.expire_all()
    row = repo.get_complaint(db, complaint_id)

    user_log = message or f"[Uploaded document: {document_name}]"
    repo.log_turn(db, complaint_id, "user", user_log)
    repo.log_turn(
        db, complaint_id, "assistant",
        result.get("assistant_message", ""), result.get("intent"),
    )

    return _to_response(row, result)


@router.post("/{complaint_id}/reset", response_model=ComplaintStateResponse)
def reset(complaint_id: int, db: Session = Depends(get_db)):
    row = repo.get_complaint(db, complaint_id)
    if row is None:
        raise HTTPException(404, "Complaint not found")
    row = repo.reset_complaint(db, row)
    return ComplaintStateResponse(
        complaint_id=row.id,
        complaint_number=row.complaint_number,
        status=ComplaintStatus.DRAFT,
        form=repo.row_to_form(row),
        risk_assessment=repo.row_to_risk(row),
        completeness=repo.row_to_completeness(row),
        duplicates=DuplicateReport(),
        assistant_message="Form cleared. Describe a new complaint or upload a document.",
    )


@router.post("/{complaint_id}/save", response_model=ComplaintStateResponse)
def save(complaint_id: int, db: Session = Depends(get_db)):
    """Commit the complaint into the QMS worklist."""
    row = repo.get_complaint(db, complaint_id)
    if row is None:
        raise HTTPException(404, "Complaint not found")
    if not row.product_name or not row.batch_lot_number:
        raise HTTPException(
            400, "Product Name and Batch/Lot Number are required before saving."
        )
    row.status = "Under Investigation"
    db.commit()
    db.refresh(row)
    return ComplaintStateResponse(
        complaint_id=row.id,
        complaint_number=row.complaint_number,
        status=ComplaintStatus(row.status),
        form=repo.row_to_form(row),
        risk_assessment=repo.row_to_risk(row),
        completeness=repo.row_to_completeness(row),
        duplicates=DuplicateReport(),
        summary=row.ai_summary,
        assistant_message=f"Complaint {row.complaint_number} saved and routed for investigation.",
    )


@router.get("/{complaint_id}/audit")
def audit_trail(complaint_id: int, db: Session = Depends(get_db)):
    """Append-only revision history — the 21 CFR Part 11 style audit trail."""
    rows = db.execute(
        select(ComplaintRevision)
        .where(ComplaintRevision.complaint_id == complaint_id)
        .order_by(ComplaintRevision.id)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "tool_used": r.tool_used,
            "user_input": r.user_input,
            "patch": r.patch,
            "changed_fields": r.changed_fields,
            "model_used": r.model_used,
            "created_at": r.created_at,
        }
        for r in rows
    ]
