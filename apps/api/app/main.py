from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.api.routes import analysis, backtests, jobs, market, notifications, positions, radar, reports, watchlist
from app.core.config import get_settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.sqlalchemy_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Taiwan Stock AI Investment Decision Assistant",
        version="0.1.0",
        description="Research assistant for Taiwan stock analysis, scoring, risk, reports, and alerts.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_api_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    app.include_router(analysis.router, prefix=settings.api_prefix)
    app.include_router(market.router, prefix=settings.api_prefix)
    app.include_router(backtests.router, prefix=settings.api_prefix)
    app.include_router(radar.router, prefix=settings.api_prefix)
    app.include_router(reports.router, prefix=settings.api_prefix)
    app.include_router(positions.router, prefix=settings.api_prefix)
    app.include_router(watchlist.router, prefix=settings.api_prefix)
    app.include_router(notifications.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
