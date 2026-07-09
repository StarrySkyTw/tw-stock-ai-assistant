from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.api.routes import analysis, backtests, jobs, market, notifications, positions, radar, reports, watchlist
from app.core.config import get_settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.sqlalchemy_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    asyncio.create_task(analysis.warm_analysis_cache())
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
    async def no_cache_dynamic_responses(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith(settings.api_prefix) or path == "/" or path.endswith(".html"):
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

    if settings.static_web_dir and settings.static_web_dir.exists():
        app.mount("/", StaticFiles(directory=settings.static_web_dir, html=True), name="static_web")

    return app


app = create_app()
