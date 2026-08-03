"""Risk assessment node — populates the AI Copilot panel.

This is a separate node rather than extra keys on the extraction schema, for
three reasons:

1. It runs on the *merged* form, so it reasons about the complete picture
   rather than only the fragment the user just typed. When the affected
   quantity is corrected from 48 capsules to 50 kg across two HDPE drums, the
   severity re-derives from the new total, which is exactly the behaviour the
   demo video shows.
2. It uses the larger reasoning model while extraction uses the fast one.
3. Reasoning and extraction fail independently. A malformed risk assessment
   does not cost the user their form data.

It is skipped when nothing on the form actually changed, so asking a question
does not burn a needless LLM call.
"""

import logging

from ...llm import registry, structured
from ...schemas import ComplaintForm, RiskAssessment
from ..prompts import QMS_CONTEXT
from ..state import ComplaintState

logger = logging.getLogger(__name__)

SYSTEM = f"""{QMS_CONTEXT}

TASK: You are the QA reviewer performing the initial risk assessment on this
complaint. Read the complaint record and produce your assessment as JSON.

Guidance for each field:

severity_classification - Apply the Critical/Major/Minor definitions above.
risk_score              - 1 to 10. Anchor points: 9-10 confirmed patient harm,
                          contamination, or wrong product/strength; 6-8 a
                          quality defect with plausible patient impact such as
                          discolouration, degradation or dissolution failure;
                          3-5 a defect confined to packaging or appearance;
                          1-2 cosmetic or administrative only.
patient_safety_impact   - One or two sentences on the realistic worst case for
                          a patient who used the affected units. Be concrete
                          and proportionate; do not catastrophise a cosmetic
                          carton dent, and do not minimise a possible
                          contamination.
regulatory_reportable   - true if this could plausibly meet the threshold for a
                          Field Alert Report or equivalent notification to a
                          regulator, false otherwise.
recommended_next_action - The single concrete next step for the QA team, in the
                          imperative. For example: "Route to QA investigation
                          and issue replacement stock", "Initiate retained
                          sample testing and quarantine remaining batch",
                          "Log and close with customer response letter".
potential_root_causes   - 2 to 4 plausible manufacturing or supply-chain causes,
                          specific to this dosage form and defect. Not generic.
                          For a discoloured capsule, think oxidation, excipient
                          interaction, moisture ingress through the blister
                          seal, or a temperature excursion in distribution.
capa_recommendations    - 2 to 4 corrective and preventive actions. Corrective
                          addresses this batch; preventive stops recurrence.
investigation_due_days  - Standard targets: Critical 3 days, Major 15 days,
                          Minor 30 days.
rationale               - Two or three sentences explaining the severity call,
                          referencing the specific facts on the complaint. This
                          is read by a human reviewer who will accept or
                          override you, so show your reasoning.

Assess only what is on the record. If the record is thin, say so in the
rationale and stay conservative rather than inventing detail.
"""


def risk_assessment_node(state: ComplaintState) -> dict:
    form: ComplaintForm = state.get("form") or ComplaintForm()

    if not form.filled_fields():
        return {"trace": ["risk_assessment (skipped: form empty)"]}

    if not state.get("updated_fields"):
        return {"trace": ["risk_assessment (skipped: no field changed)"]}

    assessment = structured(
        system=SYSTEM,
        user=(
            "Complaint record:\n"
            f"{form.model_dump_json(indent=2, exclude_none=True)}"
        ),
        schema=RiskAssessment,
        model=registry.reasoning,
    )

    # The QA assessment is authoritative over the intake severity guess: keep
    # the two panels consistent by writing it back onto the form.
    updated_form = form
    if assessment.severity_classification:
        updated_form = form.merge(
            ComplaintForm(initial_severity=assessment.severity_classification)
        )

    logger.info(
        "Risk assessed: %s (score %s)",
        assessment.severity_classification,
        assessment.risk_score,
    )
    return {
        "risk_assessment": assessment,
        "form": updated_form,
        "model_used": registry.reasoning,
        "trace": [
            f"risk_assessment → {assessment.severity_classification} "
            f"(score {assessment.risk_score})"
        ],
    }
