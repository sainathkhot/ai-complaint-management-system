"""Tests that run with no Groq key and no Postgres.

The LLM is monkeypatched, so these verify the *wiring* — routing, merging,
field-preservation, trace assembly — rather than model quality. That is the
part that can silently break, and it is the part an interviewer will poke at.

Run with:  pytest -v
"""

import warnings

warnings.filterwarnings("ignore")

import pytest

from app.schemas import ComplaintForm, RiskAssessment, RouterDecision
from app.graph.state import ComplaintState


# ---------------------------------------------------------------------------
# The core guarantee
# ---------------------------------------------------------------------------


def test_merge_preserves_unmentioned_fields():
    """The single most important behaviour in the system."""
    original = ComplaintForm(
        customer_name="Apollo Pharmacy",
        product_name="Amoxicillin Capsules",
        product_strength="500 mg",
        batch_lot_number="WRONG-123",
        quantity_affected="12 capsules",
        detailed_description="Discoloured capsules reported by pharmacist.",
        initial_severity="Major",
    )

    # Simulates: "sorry, the batch number is BMX24602 and the affected
    # quantity is 48 capsules"
    patch = ComplaintForm(batch_lot_number="BMX24602", quantity_affected="48 capsules")

    merged = original.merge(patch)

    assert merged.batch_lot_number == "BMX24602"
    assert merged.quantity_affected == "48 capsules"
    # Everything else survives untouched:
    assert merged.customer_name == "Apollo Pharmacy"
    assert merged.product_name == "Amoxicillin Capsules"
    assert merged.product_strength == "500 mg"
    assert merged.detailed_description == "Discoloured capsules reported by pharmacist."
    assert merged.initial_severity == "Major"


def test_merge_ignores_explicit_nulls():
    """A model that emits {"customer_name": null} must not blank the field."""
    original = ComplaintForm(customer_name="Cipla Ltd", product_name="Metformin HCl API")
    patch = ComplaintForm.model_validate({"customer_name": None, "product_strength": "IP/BP"})

    merged = original.merge(patch)

    assert merged.customer_name == "Cipla Ltd"
    assert merged.product_strength == "IP/BP"


def test_empty_patch_is_a_noop():
    original = ComplaintForm(product_name="Paracetamol Tablets", batch_lot_number="PCT-9001")
    assert original.merge(ComplaintForm()).model_dump() == original.model_dump()


def test_completeness_ratio():
    assert ComplaintForm().completeness_ratio() == 0.0
    partial = ComplaintForm(product_name="X", batch_lot_number="Y")
    assert 0 < partial.completeness_ratio() < 1


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_document_upload_bypasses_the_llm_router(monkeypatch):
    from app.graph.nodes import router as router_mod

    def explode(*_a, **_kw):
        raise AssertionError("Router should not call the LLM when a document is present")

    monkeypatch.setattr(router_mod, "structured", explode)

    out = router_mod.route_node({"has_document": True, "user_input": ""})
    assert out["intent"] == "extract_document"


def test_router_downgrades_impossible_intent(monkeypatch):
    """The LLM cannot pick extract_document when no file was uploaded."""
    from app.graph.nodes import router as router_mod

    monkeypatch.setattr(
        router_mod, "structured",
        lambda **_kw: RouterDecision(intent="extract_document", reasoning="confused"),
    )

    empty = router_mod.route_node(
        {"has_document": False, "user_input": "hello", "form": ComplaintForm()}
    )
    assert empty["intent"] == "log_complaint"

    populated = router_mod.route_node(
        {"has_document": False, "user_input": "hello", "form": ComplaintForm(product_name="X")}
    )
    assert populated["intent"] == "edit_complaint"


# ---------------------------------------------------------------------------
# End-to-end through the compiled graph, with every LLM call stubbed
# ---------------------------------------------------------------------------


@pytest.fixture
def stubbed_graph(monkeypatch):
    """Patch every module's LLM entry points and disable DB writes."""
    from app.graph.nodes import bonus, persist, risk, router, tools

    def fake_structured(*, system, user, schema, **_kw):
        if schema is RouterDecision:
            intent = (
                "edit_complaint"
                if "A COMPLAINT IS ALREADY ON FILE" in user
                else "log_complaint"
            )
            return RouterDecision(intent=intent, reasoning="stub")
        if schema is RiskAssessment:
            return RiskAssessment(
                severity_classification="Major",
                risk_score=7,
                recommended_next_action="Route to QA investigation and issue replacement",
                potential_root_causes=["Moisture ingress", "Excipient oxidation"],
                capa_recommendations=["Quarantine batch", "Review blister seal integrity"],
                investigation_due_days=15,
                rationale="Discolouration signals possible degradation.",
                regulatory_reportable=False,
            )
        if schema is ComplaintForm:
            if "amendment" in user.lower() or "sorry" in user.lower():
                return ComplaintForm(batch_lot_number="BMX24602", quantity_affected="48 capsules")
            return ComplaintForm(
                customer_name="Apollo Pharmacy",
                product_name="Amoxicillin Capsules",
                product_strength="500 mg",
                complaint_type="Appearance / Physical Change",
                detailed_description="Discoloured capsules observed in dispensed stock.",
                complaint_source="Phone",
            )
        return schema()

    for module in (router, tools, risk):
        monkeypatch.setattr(module, "structured", fake_structured)
    for module in (bonus, persist):
        monkeypatch.setattr(module, "complete", lambda **_kw: "Stubbed reply.")

    monkeypatch.setattr(persist, "persist_node", lambda state: {"trace": ["persist (stubbed)"]})
    monkeypatch.setattr(
        bonus, "duplicate_node",
        lambda state: {"duplicates": __import__(
            "app.schemas", fromlist=["DuplicateReport"]).DuplicateReport(),
            "trace": ["duplicate_check (stubbed)"]},
    )

    from app.graph.builder import build_graph

    return build_graph()


def test_log_then_edit_preserves_state(stubbed_graph):
    """The exact flow from the assignment's demo video."""
    config = {"configurable": {"thread_id": "test-1"}}

    first = stubbed_graph.invoke(
        {
            "complaint_id": 0,
            "user_input": "Apollo Pharmacy reported discoloured capsules in "
                          "Amoxicillin Capsules 500 mg",
            "form": ComplaintForm(),
            "has_document": False,
            "trace": [],
        },
        config=config,
    )

    assert first["form"].product_name == "Amoxicillin Capsules"
    assert first["form"].product_strength == "500 mg"
    assert first["risk_assessment"].severity_classification == "Major"
    assert "log_complaint" in first["intent"]

    # Turn two: the correction
    second = stubbed_graph.invoke(
        {
            "complaint_id": 0,
            "user_input": "sorry, the batch number is BMX24602 and the affected "
                          "quantity is 48 capsules",
            "form": first["form"],
            "risk_assessment": first["risk_assessment"],
            "has_document": False,
            "trace": [],
        },
        config={"configurable": {"thread_id": "test-2"}},
    )

    assert second["form"].batch_lot_number == "BMX24602"
    assert second["form"].quantity_affected == "48 capsules"
    # And critically, turn one's data is intact:
    assert second["form"].product_name == "Amoxicillin Capsules"
    assert second["form"].customer_name == "Apollo Pharmacy"
    assert second["form"].product_strength == "500 mg"


def test_trace_records_every_node(stubbed_graph):
    result = stubbed_graph.invoke(
        {
            "complaint_id": 0,
            "user_input": "Cipla reported off-white Metformin HCl API",
            "form": ComplaintForm(),
            "has_document": False,
            "trace": [],
        },
        config={"configurable": {"thread_id": "test-3"}},
    )
    joined = " ".join(result["trace"])
    assert "router" in joined
    assert "log_complaint_tool" in joined
    assert "risk_assessment" in joined
    assert "completeness" in joined


def test_document_path_populates_form(stubbed_graph):
    result = stubbed_graph.invoke(
        {
            "complaint_id": 0,
            "user_input": "",
            "document_text": "Product: Amoxicillin Capsules\nBatch: BMX24602",
            "document_name": "complaint.pdf",
            "has_document": True,
            "form": ComplaintForm(),
            "trace": [],
        },
        config={"configurable": {"thread_id": "test-4"}},
    )
    assert result["intent"] == "extract_document"
    assert result["form"].product_name is not None
