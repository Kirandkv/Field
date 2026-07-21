"""A2A task delegation client: Incident Commander creating a task on a peer agent.
A real HTTP call, not a function call — see docs/adr/0003-mesh-agent-protocol.md.
"""

from __future__ import annotations

import time

import httpx
from fieldforge_contracts import A2ATask, AgentCard


class DelegationError(Exception):
    pass


def delegate_task(
    agent: AgentCard, task_type: str, task_input: dict, agent_token: str, timeout: float
) -> tuple[A2ATask, float]:
    """Creates a task on the given agent. Raises DelegationError on any failure
    (agent unreachable, non-2xx response, malformed body) so the caller has one
    place to handle "delegation didn't work," matching the suite's
    no-silent-failures rule.
    """
    if task_type not in agent.supported_task_types:
        raise DelegationError(
            f"agent {agent.id!r} does not support task_type {task_type!r} "
            f"(supports: {agent.supported_task_types})"
        )

    start = time.perf_counter()
    try:
        resp = httpx.post(
            f"{agent.endpoint}/tasks",
            json={"task_type": task_type, "input": task_input},
            headers={"X-FieldForge-Agent-Token": agent_token},
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        raise DelegationError(f"agent {agent.id!r} unreachable at {agent.endpoint}: {exc}") from exc

    duration_ms = (time.perf_counter() - start) * 1000

    if resp.status_code == 403:
        raise DelegationError(f"agent {agent.id!r} rejected our credentials (403)")
    if resp.status_code >= 400:
        raise DelegationError(f"agent {agent.id!r} returned {resp.status_code}: {resp.text[:200]}")

    try:
        task = A2ATask.model_validate(resp.json())
    except Exception as exc:
        raise DelegationError(f"agent {agent.id!r} returned a malformed task: {exc}") from exc

    return task, duration_ms
