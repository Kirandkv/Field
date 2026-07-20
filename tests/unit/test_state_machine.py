from fieldforge_agent_copilot.state_machine import AgentStateMachine, InvalidTransitionError
from fieldforge_contracts import IncidentState


def test_valid_transition_succeeds():
    result = AgentStateMachine.transition(IncidentState.RECEIVED, IncidentState.TRIAGING)
    assert result == IncidentState.TRIAGING


def test_invalid_transition_raises():
    try:
        AgentStateMachine.transition(IncidentState.RECEIVED, IncidentState.COMPLETED)
        raise AssertionError("expected InvalidTransitionError")
    except InvalidTransitionError as exc:
        assert exc.current == IncidentState.RECEIVED
        assert exc.target == IncidentState.COMPLETED


def test_cannot_transition_out_of_terminal_state():
    for terminal in (IncidentState.COMPLETED, IncidentState.REJECTED, IncidentState.FAILED):
        assert AgentStateMachine.can_transition(terminal, IncidentState.TRIAGING) is False


def test_requesting_more_evidence_is_terminal_in_slice_1():
    assert AgentStateMachine.is_terminal(IncidentState.REQUESTING_MORE_EVIDENCE) is True
    assert AgentStateMachine.can_transition(
        IncidentState.REQUESTING_MORE_EVIDENCE, IncidentState.COLLECTING_EVIDENCE
    ) is False


def test_awaiting_approval_can_only_go_to_execute_or_reject():
    assert AgentStateMachine.can_transition(
        IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING_APPROVED_ACTION
    )
    assert AgentStateMachine.can_transition(IncidentState.AWAITING_APPROVAL, IncidentState.REJECTED)
    assert not AgentStateMachine.can_transition(IncidentState.AWAITING_APPROVAL, IncidentState.COMPLETED)


def test_full_happy_path_sequence_is_all_valid():
    sequence = [
        IncidentState.RECEIVED,
        IncidentState.TRIAGING,
        IncidentState.COLLECTING_EVIDENCE,
        IncidentState.ANALYZING,
        IncidentState.PROPOSING_ACTION,
        IncidentState.AWAITING_APPROVAL,
        IncidentState.EXECUTING_APPROVED_ACTION,
        IncidentState.VERIFYING,
        IncidentState.COMPLETED,
    ]
    state = sequence[0]
    for target in sequence[1:]:
        state = AgentStateMachine.transition(state, target)
    assert state == IncidentState.COMPLETED
