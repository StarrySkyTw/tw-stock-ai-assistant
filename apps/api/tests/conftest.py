import pytest

from app.core.config import get_settings
from app.services.data_providers.composite import clear_market_data_cache
from app.services.market_risk import MarketRiskEngine


@pytest.fixture(autouse=True)
def offline_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_DATA", "false")
    monkeypatch.setenv("ANALYSIS_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    clear_market_data_cache()
    MarketRiskEngine.clear_cache()
    get_settings.cache_clear()
    _reset_sqlite_schema()
    yield
    _reset_sqlite_schema()
    clear_market_data_cache()
    MarketRiskEngine.clear_cache()
    get_settings.cache_clear()


def _reset_sqlite_schema() -> None:
    try:
        from app.core.database import Base, engine

        if engine.url.get_backend_name() == "sqlite":
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
    except Exception:
        pass
