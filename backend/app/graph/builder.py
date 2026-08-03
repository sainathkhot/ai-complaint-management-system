"""StateGraph assembly.

Topology
--------

                            ┌──────────┐
                            │  router  │
                            └────┬─────┘
             ┌───────────────────┼───────────────────┬────────────────┐
             ▼                   ▼                   ▼                ▼
    ┌────────────────┐  ┌─────────────────┐  ┌────────────────┐  ┌──────────┐
    │ log_complaint  │  │ edit_complaint  │  │ extract_       │  │  answer  │
    │     _tool      │  │     _tool       │  │ document_tool  │  │ _question│
    └────────┬───────┘  └────────┬────────┘  └───────┬────────┘  └────┬─────┘
             └───────────────────┼───────────────────┘                │
                                 ▼                                    │
                        ┌────────────────┐                            │
                        │  assess_risk   │                            │
                        └────────┬───────┘                            │
                                 ▼                                    │
                        ┌────────────────┐                            │
                        │check_completen.│  (bonus)                   │
                        └────────┬───────┘                            │
                                 ▼                                    │
                        ┌────────────────┐                            │
                        │ duplicate_check│  (bonus, SQL only)         │
                        └────────┬───────┘                            │
                                 ▼                                    │
                        ┌────────────────┐                            │
                        │generate_summary│  (bonus)                   │
                        └────────┬───────┘                            │
                                 ▼                                    │
                        ┌────────────────┐                            │
                        │ compose_reply  │◀───────────────────────────┘
                        └────────┬───────┘
                                 ▼
                        ┌────────────────┐
                        │    persist     │
                        └────────┬───────┘
                                 ▼
                                END

The three mandatory tools converge on a shared post-processing chain, so the
risk assessment is guaranteed to reflect whichever tool ran. The `answer`
branch skips straight to the reply because a question changes no state.
"""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes.bonus import completeness_node, duplicate_node, summary_node
from .nodes.persist import answer_node, compose_reply_node, persist_node
from .nodes.risk import risk_assessment_node
from .nodes.router import route_edge, route_node
from .nodes.tools import (
    edit_complaint_node,
    extract_document_node,
    log_complaint_node,
)
from .state import ComplaintState

logger = logging.getLogger(__name__)


def build_graph(checkpointer=None):
    workflow = StateGraph(ComplaintState)

    workflow.add_node("router", route_node)

    # Mandatory tools
    workflow.add_node("log_complaint", log_complaint_node)
    workflow.add_node("edit_complaint", edit_complaint_node)
    workflow.add_node("extract_document", extract_document_node)
    workflow.add_node("answer_question", answer_node)

    # Shared post-processing
    workflow.add_node("assess_risk", risk_assessment_node)
    workflow.add_node("check_completeness", completeness_node)
    workflow.add_node("duplicate_check", duplicate_node)
    workflow.add_node("generate_summary", summary_node)
    workflow.add_node("compose_reply", compose_reply_node)
    workflow.add_node("persist", persist_node)

    workflow.add_edge(START, "router")

    workflow.add_conditional_edges(
        "router",
        route_edge,
        {
            "log_complaint": "log_complaint",
            "edit_complaint": "edit_complaint",
            "extract_document": "extract_document",
            "answer_question": "answer_question",
        },
    )

    # All three mutating tools converge on the assessment chain.
    for tool in ("log_complaint", "edit_complaint", "extract_document"):
        workflow.add_edge(tool, "assess_risk")

    workflow.add_edge("assess_risk", "check_completeness")
    workflow.add_edge("check_completeness", "duplicate_check")
    workflow.add_edge("duplicate_check", "generate_summary")
    workflow.add_edge("generate_summary", "compose_reply")

    # A question mutates nothing, so it bypasses the whole chain.
    workflow.add_edge("answer_question", "compose_reply")

    workflow.add_edge("compose_reply", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile(checkpointer=checkpointer or MemorySaver())


_graph = None


def get_graph():
    """Compiled once at startup and reused. Node functions are stateless, so a
    single compiled graph safely serves concurrent requests; per-conversation
    state is isolated by the checkpointer's thread_id."""
    global _graph
    if _graph is None:
        _graph = build_graph()
        logger.info("LangGraph compiled with %d nodes", len(_graph.get_graph().nodes))
    return _graph


def export_mermaid(path: str = "docs/graph.mmd") -> str:
    """Write the graph topology to a Mermaid file for the README and the demo."""
    mermaid = get_graph().get_graph().draw_mermaid()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(mermaid)
    return mermaid
