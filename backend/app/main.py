from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SpanExporter

from app.compaction import CONTEXT_WINDOW, clear_rolling_summaries
from app.conversations import router
from app.db import dispose_engine, init_db, init_engine
from app.llm import LanguageModel, load_local_env
from app.tracing import build_tracer


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_local_env()
    init_engine()
    await init_db()
    yield
    await dispose_engine()


def create_app(
    language_model: LanguageModel | None = None,
    context_window: int = CONTEXT_WINDOW,
    span_exporter: SpanExporter | None = None,
) -> FastAPI:
    app = FastAPI(title="Agent chat", lifespan=lifespan)
    app.state.language_model = language_model
    app.state.context_window = context_window
    app.state.tracer = build_tracer(span_exporter)
    clear_rolling_summaries()
    app.include_router(router)
    return app


app = create_app()
