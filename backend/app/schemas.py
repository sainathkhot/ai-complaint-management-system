"""Pydantic contracts shared by the graph, the API and (mirrored in) Redux.

Design note
-----------
`ComplaintForm` is a *patch* model: every field is Optional and nothing has a
default value that would be emitted by `model_dump(exclude_unset=True)`.

That single property is what makes the edit flow work. When the user says
"sorry, the batch number is BMX24602", the edit node returns a form containing
*only* `batch_lot_number`. Merging with `exclude_unset=True` leaves the other
thirteen fields untouched. No LLM is ever asked to echo back the full form,
which is the usual reason these systems silently wipe data.
"""

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Controlled vocabularies
#
# A pharmaceutical QMS does not accept free text in these fields. Constraining
# them to enums means the LLM output is validated against the same vocabulary
# the database and the UI dropdowns use.
# --------------------------------------------------------------------------


class ComplaintSource(str, Enum):
    EMAIL = "Email"
    PHONE = "Phone"
    PORTAL = "Customer Portal"
    FIELD_ALERT = "Field Alert"
    DISTRIBUTOR = "Distributor"
    REGULATORY = "Regulatory Authority"
    OTHER = "Other"


class ComplaintType(str, Enum):
    QUALITY_DEFECT = "Quality Defect"
    PACKAGING = "Packaging Defect"
    LABELLING = "Labelling Error"
    CONTAMINATION = "Contamination / Foreign Matter"
    APPEARANCE = "Appearance / Physical Change"
    EFFICACY = "Lack of Efficacy"
    ADVERSE_EVENT = "Adverse Event"
    SHORTAGE = "Quantity / Shortage"
    OTHER = "Other"


class Severity(str, Enum):
    """Mirrors the classification tiers used in a GMP complaint procedure."""

    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"


class Priority(str, Enum):
    URGENT = "Urgent"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ComplaintStatus(str, Enum):
    DRAFT = "Draft"
    PENDING_TRIAGE = "Pending Triage"
    UNDER_INVESTIGATION = "Under Investigation"
    CLOSED = "Closed"


# --------------------------------------------------------------------------
# The form
# --------------------------------------------------------------------------


class ComplaintForm(BaseModel):
    """The 'Log Customer Complaint' form, mirrored field-for-field in Redux."""

    model_config = ConfigDict(use_enum_values=True)

    # 1. Origin & customer details
    complaint_source: Optional[ComplaintSource] = None
    customer_name: Optional[str] = None

    # 2. Product & batch identification
    product_name: Optional[str] = None
    product_strength: Optional[str] = Field(
        default=None,
        description="Strength for FDF (e.g. '500 mg') or grade for API (e.g. 'IP/BP')",
    )
    batch_lot_number: Optional[str] = None
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None
    quantity_affected: Optional[str] = Field(
        default=None,
        description="Free text so units are preserved, e.g. '48 capsules', '50 kg (2 HDPE drums)'",
    )

    # 3. Complaint details
    complaint_type: Optional[ComplaintType] = None
    complaint_date: Optional[date] = None
    detailed_description: Optional[str] = None

    # 4. Initial assessment & priority
    initial_severity: Optional[Severity] = None
    priority: Optional[Priority] = None

    def merge(self, patch: "ComplaintForm") -> "ComplaintForm":
        """Return a new form with `patch`'s explicitly-set fields applied.

        This is the single most important line in the backend. `exclude_unset`
        means a field the model did not mention is absent from the dict, so it
        cannot overwrite an existing value with None.
        """
        merged = self.model_dump()
        merged.update(patch.model_dump(exclude_unset=True, exclude_none=True))
        return ComplaintForm.model_validate(merged)

    def filled_fields(self) -> List[str]:
        return [k for k, v in self.model_dump().items() if v not in (None, "")]

    def completeness_ratio(self) -> float:
        total = len(self.model_fields)
        return len(self.filled_fields()) / total if total else 0.0


# --------------------------------------------------------------------------
# AI Copilot risk assessment
# --------------------------------------------------------------------------


class RiskAssessment(BaseModel):
    """Regenerated from scratch on every mutation of the form."""

    model_config = ConfigDict(use_enum_values=True)

    severity_classification: Optional[Severity] = None
    risk_score: Optional[int] = Field(
        default=None, ge=1, le=10, description="1 = negligible, 10 = patient-critical"
    )
    patient_safety_impact: Optional[str] = None
    regulatory_reportable: Optional[bool] = Field(
        default=None,
        description="Whether this may trigger a Field Alert Report / Biological Product Deviation Report",
    )
    recommended_next_action: Optional[str] = None
    potential_root_causes: List[str] = Field(default_factory=list)
    capa_recommendations: List[str] = Field(default_factory=list)
    investigation_due_days: Optional[int] = None
    rationale: Optional[str] = None


# --------------------------------------------------------------------------
# Bonus feature payloads
# --------------------------------------------------------------------------


class CompletenessReport(BaseModel):
    """Bonus: Complaint Completeness Checker."""

    is_complete: bool = False
    missing_mandatory_fields: List[str] = Field(default_factory=list)
    percent_complete: int = 0
    follow_up_question: Optional[str] = None


class DuplicateMatch(BaseModel):
    complaint_id: int
    complaint_number: str
    product_name: Optional[str] = None
    batch_lot_number: Optional[str] = None
    similarity: int = Field(ge=0, le=100)
    reason: str


class DuplicateReport(BaseModel):
    """Bonus: Duplicate Complaint Detection (queries Postgres, not the LLM)."""

    has_duplicates: bool = False
    matches: List[DuplicateMatch] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------


Intent = Literal["log_complaint", "edit_complaint", "extract_document", "answer_question"]


class RouterDecision(BaseModel):
    intent: Intent
    reasoning: str = ""


# --------------------------------------------------------------------------
# API request / response
# --------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    tool_used: Optional[str] = None


class ComplaintStateResponse(BaseModel):
    """Everything the frontend needs to render both panels. Returned by every
    mutating endpoint so Redux can replace its slice wholesale."""

    complaint_id: int
    complaint_number: str
    status: ComplaintStatus
    form: ComplaintForm
    risk_assessment: RiskAssessment
    completeness: CompletenessReport
    duplicates: DuplicateReport
    summary: Optional[str] = None
    assistant_message: str
    tool_used: Optional[str] = None
    trace: List[str] = Field(
        default_factory=list, description="Ordered list of graph nodes that executed"
    )
    model_used: Optional[str] = None
    updated_fields: List[str] = Field(default_factory=list)


class MessageRequest(BaseModel):
    message: str


class ComplaintListItem(BaseModel):
    complaint_id: int
    complaint_number: str
    product_name: Optional[str]
    batch_lot_number: Optional[str]
    customer_name: Optional[str]
    initial_severity: Optional[str]
    status: str
    created_at: Any
