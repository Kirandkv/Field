from fieldforge_contracts import AnalystFinding
from fieldforge_mesh_commander import safety_officer


def _finding(rule_based: str, model_is_anomaly: bool = True) -> AnalystFinding:
    return AnalystFinding(
        device_id="FF-R07",
        corroborating_device_id="FIX-B3-02",
        rule_based_classification=rule_based,
        model_based_is_anomaly=model_is_anomaly,
        signals_agree=True,
        telemetry_summary={},
        corroborating_summary={},
        anomaly_summary={},
    )


def test_no_finding_degrades_with_approval_required():
    decision, requires_approval = safety_officer.decide(None, "agent unreachable")
    assert "degraded_no_analyst_evidence" in decision
    assert "agent unreachable" in decision
    assert requires_approval is True


def test_insufficient_evidence_requests_more_data():
    decision, requires_approval = safety_officer.decide(_finding("insufficient_evidence"), None)
    assert decision == "insufficient_evidence_request_more_data"
    assert requires_approval is True


def test_real_event_escalates_immediately():
    decision, requires_approval = safety_officer.decide(_finding("likely_real_event"), None)
    assert decision == "escalate_immediately_to_safety_manager"
    assert requires_approval is True


def test_sensor_fault_recommends_recalibration():
    decision, requires_approval = safety_officer.decide(_finding("likely_sensor_fault"), None)
    assert decision == "recommend_recalibration_pending_safety_review"
    assert requires_approval is True


def test_every_branch_requires_human_approval():
    """Incident Commander can delegate but never bypass approval — see ADR 0003
    decision 4 and the program brief's Mesh permission matrix.
    """
    for finding in (
        None,
        _finding("insufficient_evidence"),
        _finding("likely_real_event"),
        _finding("likely_sensor_fault"),
    ):
        _, requires_approval = safety_officer.decide(finding, "err" if finding is None else None)
        assert requires_approval is True
