"""SQLAlchemy ORM models.

`complaint_revisions` is deliberately append-only. A pharmaceutical QMS running
under 21 CFR Part 11 needs an audit trail showing who changed what and when,
and it must never be overwritten. Since every mutation here flows through the
graph as a patch, capturing that patch gives us the audit trail almost for free.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="Draft")

    # --- Form fields (typed columns so they are queryable, e.g. for dedup) ---
    complaint_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_strength: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_lot_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    manufacturing_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    quantity_affected: Mapped[str | None] = mapped_column(String(128), nullable=True)
    complaint_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    complaint_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    detailed_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_severity: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- AI output (schemaless: shape may evolve, and it is never queried) ---
    risk_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    completeness: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_document_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow
    )

    revisions: Mapped[list["ComplaintRevision"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintRevision.id"
    )
    messages: Mapped[list["ChatTurn"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="ChatTurn.id"
    )

    FORM_COLUMNS = (
        "complaint_source",
        "customer_name",
        "product_name",
        "product_strength",
        "batch_lot_number",
        "manufacturing_date",
        "expiry_date",
        "quantity_affected",
        "complaint_type",
        "complaint_date",
        "detailed_description",
        "initial_severity",
        "priority",
    )


class ComplaintRevision(Base):
    """One row per AI mutation. Never updated, never deleted."""

    __tablename__ = "complaint_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"))
    tool_used: Mapped[str] = mapped_column(String(64))
    user_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    patch: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_fields: Mapped[dict] = mapped_column(JSON, default=list)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    complaint: Mapped[Complaint] = relationship(back_populates="revisions")


class ChatTurn(Base):
    __tablename__ = "chat_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    complaint: Mapped[Complaint] = relationship(back_populates="messages")
