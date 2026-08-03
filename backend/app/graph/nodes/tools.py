"""The three mandatory AI tools from the assignment brief.

    1. log_complaint_tool     - prompt in, populated form out
    2. edit_complaint_tool    - natural-language amendment, other fields preserved
    3. document_extraction_tool - PDF/email in, populated form out

All three share the same contract: produce a `ComplaintForm` *patch*, merge it
into the form already in state, and report which fields actually changed. The
merge lives in `_apply_patch` so the preservation guarantee is implemented once
rather than three times.
"""

import logging
from datetime import date

from ...llm import registry, structured
from ...schemas import ComplaintForm
from ..prompts import EXTRACTION_RULES, QMS_CONTEXT, TODAY_HINT
from ..state import ComplaintState

logger = logging.getLogger(__name__)


def _apply_patch(state: ComplaintState, patch: ComplaintForm, tool: str) -> dict:
    """Merge a patch into the current form and compute the diff.

    `ComplaintForm.merge` uses `model_dump(exclude_unset=True, exclude_none=True)`,
    so a field the LLM did not mention cannot overwrite an existing value. This
    is what makes "sorry, the batch number is BMX24602" change one field and
    leave the other twelve alone.
    """
    current = state.get("form") or ComplaintForm()
    merged = current.merge(patch)

    before = current.model_dump()
    after = merged.model_dump()
    changed = [k for k in after if before.get(k) != after.get(k)]

    logger.info("%s changed %d field(s): %s", tool, len(changed), changed)
    return {
        "form": merged,
        "patch": patch.model_dump(exclude_unset=True, exclude_none=True, mode="json"),
        "updated_fields": changed,
        "model_used": registry.extraction,
        "trace": [f"{tool} (updated: {', '.join(changed) if changed else 'nothing'})"],
    }


# ---------------------------------------------------------------------------
# Tool 1 — log complaint
# ---------------------------------------------------------------------------

LOG_SYSTEM = f"""{QMS_CONTEXT}

TASK: The user has described a customer complaint in free text. Extract every
complaint field the text supports and return them as JSON.

{EXTRACTION_RULES}

Additionally:
- Set `complaint_source` based on how the complaint appears to have arrived. If
  the user does not say, choose the most plausible option rather than omitting
  it (a pharmacy phoning in a report is "Phone"; a forwarded message is "Email").
- Set `complaint_date` to today unless the text states otherwise.
- Set `initial_severity` and `priority` using the classification guidance above.
- If the customer is named (a pharmacy, hospital, distributor), that is
  `customer_name`.
"""


def log_complaint_node(state: ComplaintState) -> dict:
    user_input = state.get("user_input", "")
    patch = structured(
        system=LOG_SYSTEM + "\n" + TODAY_HINT.format(today=date.today().isoformat()),
        user=f"Complaint reported by the user:\n\n{user_input}",
        schema=ComplaintForm,
        model=registry.extraction,
    )
    return _apply_patch(state, patch, "log_complaint_tool")


# ---------------------------------------------------------------------------
# Tool 2 — edit complaint
# ---------------------------------------------------------------------------

EDIT_SYSTEM = f"""{QMS_CONTEXT}

TASK: A complaint is already on file. The user is amending it. Return JSON
containing ONLY the fields the user is changing or adding.

This is the most important rule in the system: DO NOT echo back fields the user
did not mention. If the user says "sorry, the batch number is BMX24602 and the
affected quantity is 48 capsules", your entire response is:

    {{"batch_lot_number": "BMX24602", "quantity_affected": "48 capsules"}}

Nothing else. Every key you include overwrites stored data, so include the
minimum. Every key you omit is preserved automatically.

If the amendment materially changes the risk picture — a much larger affected
quantity, a newly reported patient impact, a contamination detail — you may
also include `initial_severity` and `priority` at their new levels. Otherwise
leave them out.

{EXTRACTION_RULES}
"""


def edit_complaint_node(state: ComplaintState) -> dict:
    current = state.get("form") or ComplaintForm()
    context = (
        "Complaint currently on file:\n"
        f"{current.model_dump_json(indent=2, exclude_none=True)}\n\n"
        f"User's amendment:\n{state.get('user_input', '')}"
    )
    patch = structured(
        system=EDIT_SYSTEM + "\n" + TODAY_HINT.format(today=date.today().isoformat()),
        user=context,
        schema=ComplaintForm,
        model=registry.extraction,
    )
    return _apply_patch(state, patch, "edit_complaint_tool")


# ---------------------------------------------------------------------------
# Tool 3 — document extraction
# ---------------------------------------------------------------------------

DOC_SYSTEM = f"""{QMS_CONTEXT}

TASK: Text has been extracted from a customer complaint document (a PDF letter,
a complaint form, or a forwarded email). Pull the complaint fields out of it.

{EXTRACTION_RULES}

Document-specific guidance:
- These documents often use labelled fields ("Batch/Lot No.:", "Product:",
  "Mfg. Date:"). Trust an explicit label over your own inference.
- Letterheads, footers, reference numbers and signature blocks are not
  complaint data. Ignore them.
- The sender's organisation is `customer_name`, not the manufacturer's.
- If the document is an email, `complaint_source` is "Email".
- Dates appear in many formats (12-Jul-2026, 12/07/2026, 2026-07-12). Normalise
  to YYYY-MM-DD, reading ambiguous numeric dates as DD/MM/YYYY, which is the
  Indian and European convention used across this document set.
"""


def extract_document_node(state: ComplaintState) -> dict:
    text = state.get("document_text") or ""
    if not text.strip():
        return {
            "assistant_message": (
                "I could not read any text from that file. If it is a scanned image, "
                "please paste the complaint text instead."
            ),
            "updated_fields": [],
            "trace": ["document_extraction_tool (no text found)"],
        }

    # Guard the context window. 12k characters comfortably covers a multi-page
    # complaint letter and stays inside the smallest model's window.
    excerpt = text[:12000]

    user = (
        f"Document filename: {state.get('document_name') or 'complaint.pdf'}\n\n"
        f"--- BEGIN DOCUMENT ---\n{excerpt}\n--- END DOCUMENT ---"
    )
    patch = structured(
        system=DOC_SYSTEM + "\n" + TODAY_HINT.format(today=date.today().isoformat()),
        user=user,
        schema=ComplaintForm,
        model=registry.extraction,
    )
    result = _apply_patch(state, patch, "document_extraction_tool")

    # A document that arrives with a covering instruction gets both treatments:
    # extract from the file, then apply the typed amendment on top.
    return result
