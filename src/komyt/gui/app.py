"""Komyt GUI — FastAPI web dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from komyt.core.config import GUIConfig, KomytConfig
from komyt.core.models import PipelineResult, TaskStatus

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class TaskEntry:
    """A tracked task displayed in the dashboard."""

    ticket_id: str
    title: str
    status: str
    branch: str = ""
    pr_url: str | None = None
    score: int | None = None
    tokens: int = 0
    cost: float = 0.0
    duration: float = 0.0
    updated_at: str = ""


class DashboardState:
    """In-memory state for the dashboard (replaced by DB in production)."""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskEntry] = {}
        self.events: deque[dict[str, str]] = deque(maxlen=100)
        self._subscribers: list[asyncio.Queue[dict[str, str]]] = []

    def upsert_task(self, entry: TaskEntry) -> None:
        entry.updated_at = datetime.now().isoformat(timespec="seconds")
        self.tasks[entry.ticket_id] = entry
        self._publish({"event": "task_update", "data": json.dumps(asdict(entry))})

    def record_from_result(self, result: PipelineResult) -> None:
        entry = TaskEntry(
            ticket_id=result.ticket.id,
            title=result.ticket.title,
            status=result.status.value,
            branch=result.branch_name,
            pr_url=result.pr_url,
            tokens=result.total_tokens,
            cost=result.estimated_cost,
            duration=result.duration_seconds,
        )
        self.upsert_task(entry)

    def _publish(self, event: dict[str, str]) -> None:
        self.events.append(event)
        for q in self._subscribers:
            q.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[dict[str, str]]:
        q: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, str]]) -> None:
        self._subscribers.remove(q)


def create_app(config: KomytConfig | None = None, state: DashboardState | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = config or KomytConfig()
    dashboard = state or DashboardState()

    app = FastAPI(title="Komyt Dashboard", version="0.1.0")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        tasks = sorted(
            dashboard.tasks.values(),
            key=lambda t: t.updated_at,
            reverse=True,
        )
        return templates.TemplateResponse(request, "index.html", {
            "tasks": tasks,
            "config": cfg,
        })

    @app.get("/task/{ticket_id}", response_class=HTMLResponse)
    async def task_detail(request: Request, ticket_id: str) -> HTMLResponse:
        task = dashboard.tasks.get(ticket_id)
        return templates.TemplateResponse(request, "task_detail.html", {
            "task": task,
            "ticket_id": ticket_id,
        })

    @app.get("/config", response_class=HTMLResponse)
    async def config_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "config.html", {
            "config": cfg,
        })

    @app.get("/api/tasks")
    async def api_tasks() -> list[dict]:  # type: ignore[type-arg]
        return [asdict(t) for t in dashboard.tasks.values()]

    @app.get("/api/tasks/{ticket_id}")
    async def api_task(ticket_id: str) -> dict:  # type: ignore[type-arg]
        task = dashboard.tasks.get(ticket_id)
        if task is None:
            return {"error": "not found"}
        return asdict(task)

    @app.get("/api/events")
    async def sse_events(request: Request) -> EventSourceResponse:
        async def event_generator() -> AsyncGenerator[dict[str, str], None]:
            q = dashboard.subscribe()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=30.0)
                        yield event
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": ""}
            finally:
                dashboard.unsubscribe(q)

        return EventSourceResponse(event_generator())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
