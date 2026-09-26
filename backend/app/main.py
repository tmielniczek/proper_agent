from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.conversations import router
from app.db import dispose_engine, init_db, init_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_engine()
    await init_db()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Agent chat", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
