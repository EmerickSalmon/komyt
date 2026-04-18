"""Functional tests for the GUI — test HTTP routes with real FastAPI test client."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from komyt.core.config import KomytConfig
from komyt.gui.app import DashboardState, TaskEntry, create_app


@pytest.fixture
def state() -> DashboardState:
    s = DashboardState()
    s.upsert_task(TaskEntry(
        ticket_id="t1", title="Add authentication", status="completed",
        branch="komyt/feature/auth", pr_url="https://github.com/org/repo/pull/1",
        tokens=10000, cost=0.10, duration=120.0,
    ))
    s.upsert_task(TaskEntry(
        ticket_id="t2", title="Fix login bug", status="failed",
        branch="komyt/fix/login", tokens=5000, cost=0.05, duration=60.0,
    ))
    return s


@pytest.fixture
def app(state: DashboardState):  # type: ignore[no-untyped-def]
    return create_app(config=KomytConfig(), state=state)


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.functional
class TestDashboardRoutes:
    async def test_index_returns_html(self, client: AsyncClient) -> None:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Komyt" in resp.text

    async def test_index_lists_tasks(self, client: AsyncClient) -> None:
        resp = await client.get("/")
        assert "Add authentication" in resp.text
        assert "Fix login bug" in resp.text

    async def test_task_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/task/t1")
        assert resp.status_code == 200
        assert "Add authentication" in resp.text
        assert "komyt/feature/auth" in resp.text
        assert "10,000" in resp.text

    async def test_task_detail_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/task/nonexistent")
        assert resp.status_code == 200
        assert "not found" in resp.text.lower()

    async def test_config_page(self, client: AsyncClient) -> None:
        resp = await client.get("/config")
        assert resp.status_code == 200
        assert "@komyt" in resp.text
        assert "claude-sonnet-4-6" in resp.text

    async def test_health_endpoint(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.functional
class TestAPIRoutes:
    async def test_api_tasks(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        ids = {t["ticket_id"] for t in data}
        assert ids == {"t1", "t2"}

    async def test_api_task_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks/t1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Add authentication"
        assert data["status"] == "completed"

    async def test_api_task_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status_code == 200
        assert resp.json() == {"error": "not found"}


@pytest.mark.functional
class TestEmptyDashboard:
    async def test_empty_state(self) -> None:
        app = create_app(config=KomytConfig(), state=DashboardState())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "@komyt" in resp.text
