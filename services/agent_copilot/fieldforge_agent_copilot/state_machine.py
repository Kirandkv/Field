"""Explicit incident state machine — see docs/adr/0002-copilot-agent-architecture.md
decision 1 for why this is hand-rolled instead of a graph framework.

Every transition is a table lookup. There is no code path that mutates an Incident's
state outside of `AgentStateMachine.transition()`, and every transition not in
TRANSITIONS raises — this is what "invalid transitions must be rejected and tested"
means concretely (see tests/unit/test_state_machine.py).
"""

from __future__ import annotations

from fieldforge_contracts import IncidentState

TERMINAL_STATES = frozenset(
    {
        IncidentState.COMPLETED,
        IncidentState.REJECTED,
        IncidentState.FAILED,
        # REQUESTING_MORE_EVIDENCE is terminal in slice 1: the investigation stops
        # pending new evidence rather than looping automatically. An automatic
        # retry/escalation policy is planned (M2) — looping without one risks the
        # infinite-agent-loop failure mode the threat model explicitly calls out.
        IncidentState.REQUESTING_MORE_EVIDENCE,
    }
)

TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.RECEIVED: frozenset({IncidentState.TRIAGING}),
    IncidentState.TRIAGING: frozenset(
        {IncidentState.COLLECTING_EVIDENCE, IncidentState.FAILED}
    ),
    IncidentState.COLLECTING_EVIDENCE: frozenset(
        {IncidentState.ANALYZING, IncidentState.FAILED}
    ),
    IncidentState.ANALYZING: frozenset(
        {
            IncidentState.REQUESTING_MORE_EVIDENCE,
            IncidentState.PROPOSING_ACTION,
            IncidentState.FAILED,
        }
    ),
    IncidentState.PROPOSING_ACTION: frozenset(
        {IncidentState.AWAITING_APPROVAL, IncidentState.FAILED}
    ),
    IncidentState.AWAITING_APPROVAL: frozenset(
        {IncidentState.EXECUTING_APPROVED_ACTION, IncidentState.REJECTED}
    ),
    IncidentState.EXECUTING_APPROVED_ACTION: frozenset(
        {IncidentState.VERIFYING, IncidentState.FAILED}
    ),
    IncidentState.VERIFYING: frozenset({IncidentState.COMPLETED, IncidentState.FAILED}),
    IncidentState.COMPLETED: frozenset(),
    IncidentState.REJECTED: frozenset(),
    IncidentState.FAILED: frozenset(),
    IncidentState.REQUESTING_MORE_EVIDENCE: frozenset(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: IncidentState, target: IncidentState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid transition: {current.value} -> {target.value}")


class AgentStateMachine:
    @staticmethod
    def is_terminal(state: IncidentState) -> bool:
        return state in TERMINAL_STATES

    @staticmethod
    def can_transition(current: IncidentState, target: IncidentState) -> bool:
        return target in TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: IncidentState, target: IncidentState) -> IncidentState:
        if not cls.can_transition(current, target):
            raise InvalidTransitionError(current, target)
        return target
