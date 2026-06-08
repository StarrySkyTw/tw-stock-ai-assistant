import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def offline_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_DATA", "false")
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
