"""HTTP API entry point — mirrors every Telegram bot feature over REST."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from contextlib import asynccontextmanager

from api.routers import backup, daily, learn, questions, stats
from shared.factory import build_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = build_engine()
    yield


app = FastAPI(
    title="German Learning Bot API",
    description="REST interface to the same learning engine used by the Telegram bot.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(daily.router)
app.include_router(learn.router)
app.include_router(stats.router)
app.include_router(questions.router)
app.include_router(backup.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
