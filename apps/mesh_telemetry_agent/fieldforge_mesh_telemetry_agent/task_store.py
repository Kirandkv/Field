"""In-memory task store. Tasks in this slice complete synchronously within the
request that creates them (ADR 0003 decision 6), so there is no durability
requirement a SQLite store would earn its keep on yet — unlike Copilot's approvals,
which are an audit record, a Telemetry Analyst task is a disposable computation. A
persisted task history is a real M2 candidate once tasks run asynchronously.
"""

from __future__ import annotations

from fieldforge_contracts import A2ATask


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, A2ATask] = {}

    def save(self, task: A2ATask) -> None:
        self._tasks[task.id] = task

    def get(self, task_id: str) -> A2ATask | None:
        return self._tasks.get(task_id)

    def list(self) -> list[A2ATask]:
        return list(self._tasks.values())
