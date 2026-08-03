"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .graph.builder import get_graph
from .llm import registry
from .routers import complaints

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    init_db()
    registry.resolve()  # resolve Groq models once, log any spec deviation
    get_graph()  # compile the graph once so the first request is not slow
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered customer complaint intake for pharmaceutical (API & FDF) "
        "manufacturing. LangGraph + Groq + FastAPI + Postgres."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints.router)


@app.get("/api/health", tags=["system"])
def health():
    """Reports which models were actually resolved — useful in the demo to show
    the gemma2-9b-it fallback happening live."""
    return {
        "status": "ok",
        "models": {
            "reasoning": registry.reasoning,
            "extraction": registry.extraction,
            "spec_model_available": "gemma2-9b-it" in registry.live_models,
            "live_model_count": len(registry.live_models),
        },
        "graph_nodes": list(get_graph().get_graph().nodes),
    }


@app.get("/api/graph", tags=["system"])
def graph_topology():
    """Mermaid source for the workflow diagram."""
    return {"mermaid": get_graph().get_graph().draw_mermaid()}
