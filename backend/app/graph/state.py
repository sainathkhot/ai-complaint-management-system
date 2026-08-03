"""The graph state.

Everything the assistant knows about the complaint lives in one typed dict that
flows through every node. The form panel on the left of the UI is literally a
render of `state["form"]`, and the copilot panel on the right is a render of
`state["risk_assessment"]`. There is no other source of truth in the request
path, which is what enforces the assignment's "you must not fill the left form
manually" constraint at the architecture level rather than by disabling inputs.
"""

from typing import Annotated, List, Optional, TypedDict

from ..schemas import (
    ComplaintForm,
    CompletenessReport,
    DuplicateReport,
    RiskAssessment,
)


def append(existing: List[str], new: List[str]) -> List[str]:
    """Reducer so nodes can append to the execution trace without clobbering it."""
    return (existing or []) + (new or [])


class ComplaintState(TypedDict, total=False):
    # --- Identity ---
    complaint_id: int
    complaint_number: str

    # --- Input for this turn ---
    user_input: str
    document_text: Optional[str]
    document_name: Optional[str]
    has_document: bool

    # --- Working data (the two UI panels) ---
    form: ComplaintForm
    risk_assessment: RiskAssessment
    completeness: CompletenessReport
    duplicates: DuplicateReport
    summary: Optional[str]

    # --- Routing / bookkeeping ---
    intent: str
    intent_reasoning: str
    patch: dict
    updated_fields: List[str]
    assistant_message: str
    model_used: str
    trace: Annotated[List[str], append]
