from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router
from app.api.error_handlers import install as install_error_handlers
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="GridWise Optimizer",
    description="LLM-Assisted 24-Hour Energy Optimization for BUP CSE Fest 2026",
    version="1.0.0",
    lifespan=lifespan,
)

install_error_handlers(app)
app.include_router(router)
