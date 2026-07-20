import pytest
from fieldforge_agent_copilot import orchestrator
from fieldforge_agent_copilot.telemetry_store import TelemetryStore
from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import Alert, IncidentClassification, IncidentState, SensorMetric

UNREACHABLE_DOCS_URL = "http://127.0.0.1:1"  # port 1 is never a real HTTP server


@pytest.fixture(scope="module")
def store():
    return TelemetryStore()


@pytest.fixture(scope="module")
def detector(store):
    d = DeviceAnomalyDetector()
    for device_id in ("FF-R07", "FIX-B3-02", "FIX-B3-01"):
        d.fit(device_id, [p.value for p in store.get_history(device_id)])
    return d


def _alert_for(store, scenario_id):
    scenario = next(s for s in store.list_alert_scenarios() if s["id"] == scenario_id)
    return Alert(
        device_id=scenario["device_id"],
        metric=SensorMetric.METHANE_PPM,
        value=scenario["value"],
        window_seconds=scenario["window_seconds"],
        triggered_at=scenario["triggered_at"],
        corroborating_device_id=scenario.get("corroborating_device_id"),
    ), scenario


@pytest.mark.parametrize(
    "scenario_id,expected_classification,expected_state",
    [
        ("alert-2026-06-14", IncidentClassification.LIKELY_SENSOR_FAULT, IncidentState.AWAITING_APPROVAL),
        ("alert-2026-04-18", IncidentClassification.LIKELY_SENSOR_FAULT, IncidentState.AWAITING_APPROVAL),
        ("alert-2026-07-08", IncidentClassification.LIKELY_REAL_EVENT, IncidentState.AWAITING_APPROVAL),
        (
            "alert-2026-07-10",
            IncidentClassification.INSUFFICIENT_EVIDENCE,
            IncidentState.REQUESTING_MORE_EVIDENCE,
        ),
    ],
)
def test_flagship_scenarios_classify_correctly(
    store, detector, scenario_id, expected_classification, expected_state
):
    alert, _ = _alert_for(store, scenario_id)
    incident, approval = orchestrator.investigate(alert, store, detector, docs_api_url=UNREACHABLE_DOCS_URL)
    assert incident.classification == expected_classification
    assert incident.state == expected_state
    if expected_state == IncidentState.AWAITING_APPROVAL:
        assert approval is not None
        assert approval.incident_id == incident.id
    else:
        assert approval is None


def test_real_event_produces_high_risk_proposal(store, detector):
    alert, _ = _alert_for(store, "alert-2026-07-08")
    incident, approval = orchestrator.investigate(alert, store, detector, docs_api_url=UNREACHABLE_DOCS_URL)
    assert approval.risk_level.value == "high"


def test_unknown_device_transitions_to_failed(store, detector):
    alert = Alert(
        device_id="NOT-A-REAL-DEVICE",
        metric=SensorMetric.METHANE_PPM,
        value=1200,
        window_seconds=40,
        triggered_at="2026-07-15T10:00:00Z",
        corroborating_device_id="FIX-B3-02",
    )
    incident, approval = orchestrator.investigate(alert, store, detector, docs_api_url=UNREACHABLE_DOCS_URL)
    assert incident.state == IncidentState.FAILED
    assert incident.error is not None
    assert approval is None


def test_investigation_completes_without_crashing_when_docs_api_unavailable(store, detector):
    """Docs API being down must degrade gracefully (no SOP evidence, no crash), not
    raise — this is the failure mode ADR 0002 decision 2 documents.
    """
    alert, _ = _alert_for(store, "alert-2026-06-14")
    incident, approval = orchestrator.investigate(alert, store, detector, docs_api_url=UNREACHABLE_DOCS_URL)
    assert incident.state == IncidentState.AWAITING_APPROVAL
    sop_evidence = [e for e in incident.evidence if e.kind.value == "sop_citation"]
    assert sop_evidence == []


def test_no_corroborating_device_is_insufficient_evidence(store, detector):
    alert = Alert(
        device_id="FF-R07",
        metric=SensorMetric.METHANE_PPM,
        value=1100,
        window_seconds=40,
        triggered_at="2026-06-14T14:32:00Z",
        corroborating_device_id=None,
    )
    incident, approval = orchestrator.investigate(alert, store, detector, docs_api_url=UNREACHABLE_DOCS_URL)
    assert incident.classification == IncidentClassification.INSUFFICIENT_EVIDENCE
    assert incident.state == IncidentState.REQUESTING_MORE_EVIDENCE
