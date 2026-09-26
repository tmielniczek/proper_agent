from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.conversations import router
from app.db import dispose_engine, init_db, init_engine
from app.llm import LanguageModel, load_local_env


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_local_env()
    init_engine()
    await init_db()
    yield
    await dispose_engine()


def create_app(language_model: LanguageModel | None = None) -> FastAPI:
    app = FastAPI(title="Agent chat", lifespan=lifespan)
    app.state.language_model = language_model
    app.include_router(router)
    return app


app = create_app()
