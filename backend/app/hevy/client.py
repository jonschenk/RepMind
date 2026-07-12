"""Isolated Hevy API client. Every Hevy-specific quirk is contained here so the rest of
the app never talks HTTP to Hevy directly, and so this file is easy to patch when the
(explicitly early-stage) Hevy API changes.

Quirks encoded:
- Auth header is `api-key` (not Bearer).
- GET /v1/workouts pageSize maxes at 10; exercise_templates maxes at 100.
- POST/PUT /v1/routines bodies must be wrapped in {"routine": {...}} (see schemas.py).
- `@` in notes silently 400s (sanitized in schemas.py).
- No DELETE endpoints exist for anything — none are implemented.
- DRY_RUN: write calls log the resolved payload and return a fake id instead of pushing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional

import httpx

from app.config import Settings

logger = logging.getLogger("repmind.hevy")

WORKOUTS_PAGE_SIZE = 10  # Hevy max for /v1/workouts
TEMPLATES_PAGE_SIZE = 100  # Hevy max for /v1/exercise_templates


class HevyError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class HevyClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.hevy_base_url.rstrip("/")
        self._dry_run = settings.dry_run
        if not settings.hevy_api_key:
            raise HevyError("HEVY_API_KEY is not set")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"api-key": self._settings.hevy_api_key, "accept": "application/json"},
            timeout=30.0,
        )

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        async with self._client() as client:
            resp = await client.get(path, params=params)
        if resp.status_code >= 400:
            raise HevyError(
                f"GET {path} failed ({resp.status_code}): {resp.text[:300]}",
                resp.status_code,
            )
        return resp.json()

    # --- Reads -------------------------------------------------------------------

    async def get_workout_count(self) -> int:
        data = await self._get("/v1/workouts/count")
        return int(data.get("workout_count", data.get("count", 0)))

    async def iter_workouts(self) -> AsyncIterator[dict]:
        """Yield every workout across all pages (newest first, per Hevy)."""
        page = 1
        while True:
            data = await self._get(
                "/v1/workouts", params={"page": page, "pageSize": WORKOUTS_PAGE_SIZE}
            )
            workouts = data.get("workouts", [])
            for w in workouts:
                yield w
            page_count = int(data.get("page_count", 1))
            if page >= page_count or not workouts:
                break
            page += 1

    async def get_workout(self, workout_id: str) -> dict:
        return await self._get(f"/v1/workouts/{workout_id}")

    async def iter_workout_events(self, since: str) -> AsyncIterator[dict]:
        """Delta sync. `since` is an ISO-8601 date string. Yields event objects with
        type 'updated' (carries a `workout`) or 'deleted' (carries an `id`)."""
        page = 1
        while True:
            data = await self._get(
                "/v1/workouts/events",
                params={"page": page, "pageSize": WORKOUTS_PAGE_SIZE, "since": since},
            )
            events = data.get("events", [])
            for e in events:
                yield e
            page_count = int(data.get("page_count", 1))
            if page >= page_count or not events:
                break
            page += 1

    async def iter_exercise_templates(self) -> AsyncIterator[dict]:
        page = 1
        while True:
            data = await self._get(
                "/v1/exercise_templates",
                params={"page": page, "pageSize": TEMPLATES_PAGE_SIZE},
            )
            templates = data.get("exercise_templates", [])
            for t in templates:
                yield t
            page_count = int(data.get("page_count", 1))
            if page >= page_count or not templates:
                break
            page += 1

    async def get_routines(self) -> list[dict]:
        routines: list[dict] = []
        page = 1
        while True:
            data = await self._get("/v1/routines", params={"page": page, "pageSize": 10})
            batch = data.get("routines", [])
            routines.extend(batch)
            page_count = int(data.get("page_count", 1))
            if page >= page_count or not batch:
                break
            page += 1
        return routines

    async def get_routine_folders(self) -> list[dict]:
        data = await self._get("/v1/routine_folders", params={"page": 1, "pageSize": 10})
        return data.get("routine_folders", [])

    async def get_body_measurements(self, max_pages: int = 6) -> list[dict]:
        out: list[dict] = []
        page = 1
        while page <= max_pages:
            data = await self._get(
                "/v1/body_measurements", params={"page": page, "pageSize": 10}
            )
            batch = data.get("body_measurements", [])
            out.extend(batch)
            page_count = int(data.get("page_count", 1))
            if page >= page_count or not batch:
                break
            page += 1
        return out

    async def get_exercise_history(
        self,
        template_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        params: dict = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        data = await self._get(f"/v1/exercise_history/{template_id}", params=params or None)
        return data.get("exercise_history", [])

    # --- Writes (gated by DRY_RUN) ----------------------------------------------

    async def create_routine(self, body: dict) -> dict:
        """`body` must already be the wrapped {"routine": {...}} payload from
        schemas.build_routine_body()."""
        return await self._write("POST", "/v1/routines", body)

    async def update_routine(self, routine_id: str, body: dict) -> dict:
        return await self._write("PUT", f"/v1/routines/{routine_id}", body)

    async def _write(self, method: str, path: str, body: dict) -> dict:
        if self._dry_run:
            fake_id = f"dry-run-{uuid.uuid4().hex[:8]}"
            logger.info(
                "[DRY_RUN] %s %s not sent. Resolved payload: %s", method, path, body
            )
            return {"id": fake_id, "dry_run": True, "sent_payload": body}

        async with self._client() as client:
            resp = await client.request(
                method, path, json=body, headers={"content-type": "application/json"}
            )
        if resp.status_code >= 400:
            raise HevyError(
                f"{method} {path} failed ({resp.status_code}): {resp.text[:300]}",
                resp.status_code,
            )
        data = resp.json()
        # Hevy returns the created/updated routine; surface its id.
        routine = data.get("routine", data)
        if isinstance(routine, list) and routine:
            routine = routine[0]
        return {"id": routine.get("id"), "dry_run": False, "routine": routine}
