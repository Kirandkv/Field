"""Generates synthetic device registry + telemetry history + alert scenarios for
FieldForge Copilot into data/samples/telemetry/.

Deterministic (seeded RNG), not random per run, so eval gold outcomes stay stable.
The 2026-06-14 FF-R07 incident matches the narrative already written into
data/samples/inspection_report_2026_06_14_site_b.md (FieldForge Docs corpus) — running
Copilot's flagship scenario and then asking FieldForge Docs about the same incident
should tell a consistent story. See DATA_CARD.md.

Usage: python data/generators/generate_telemetry.py
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "telemetry"
SEED = 20260714

DEVICES = [
    {
        "id": "FF-R07",
        "name": "FF-R07 Mobile Inspection Robot",
        "device_type": "mobile_robot",
        "site": "site-b",
    },
    {"id": "FIX-B3-02", "name": "Fixed Sensor B3-02", "device_type": "fixed_sensor", "site": "site-b"},
    {"id": "FIX-B3-01", "name": "Fixed Sensor B3-01", "device_type": "fixed_sensor", "site": "site-b"},
]

# Covers every scenario date below (2026-04-18 through 2026-07-10) with margin on
# both ends, so every alert window has real corroborating baseline coverage.
BASELINE_START = datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
BASELINE_DAYS = 105

# Fixed sensors sample continuously (manual_ff_env_sensor_array.md: "Sampling
# interval: 10 seconds"); slice 1 uses a coarser 60s synthetic interval to keep the
# committed corpus small while still guaranteeing dense-enough coverage that a
# multi-minute corroboration window (see orchestrator.py) reliably contains points.
# The mobile robot only reports while actively surveying, so its baseline is sparser
# — 30 minutes stands in for periodic survey rounds, not continuous streaming.
BASELINE_INTERVAL_MINUTES = {
    "mobile_robot": 30,
    "fixed_sensor": 10,
}


def _baseline_series(device_id: str, device_type: str, rng: random.Random) -> list[dict]:
    interval_minutes = BASELINE_INTERVAL_MINUTES[device_type]
    points = []
    n = int(BASELINE_DAYS * 24 * 60 / interval_minutes)
    t = BASELINE_START
    for _ in range(n):
        value = max(0.0, rng.gauss(10.0, 2.0))
        points.append(
            {
                "device_id": device_id,
                "metric": "methane_ppm",
                "value": round(value, 1),
                "timestamp": t.isoformat(),
                "quality_flag": "ok",
            }
        )
        t += timedelta(minutes=interval_minutes)
    return points


def _spike_series(
    device_id: str, center: datetime, peak_ppm: float, duration_s: float, rng: random.Random
) -> list[dict]:
    points = []
    steps = max(3, int(duration_s // 5))
    start = center - timedelta(seconds=duration_s / 2)
    for i in range(steps):
        t = start + timedelta(seconds=i * (duration_s / steps))
        value = peak_ppm + rng.gauss(0, peak_ppm * 0.02)
        points.append(
            {
                "device_id": device_id,
                "metric": "methane_ppm",
                "value": round(max(0.0, value), 1),
                "timestamp": t.isoformat(),
                "quality_flag": "ok",
            }
        )
    return points


def _stale_series(device_id: str, center: datetime, last_good_value: float, hours_stale: float) -> list[dict]:
    stale_time = center - timedelta(hours=hours_stale)
    return [
        {
            "device_id": device_id,
            "metric": "methane_ppm",
            "value": last_good_value,
            "timestamp": stale_time.isoformat(),
            "quality_flag": "stale",
        }
    ]


def build_telemetry() -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    series: dict[str, list[dict]] = {
        d["id"]: _baseline_series(d["id"], d["device_type"], rng) for d in DEVICES
    }

    # Scenario 1 (flagship, matches inspection_report_2026_06_14_site_b.md):
    # FF-R07 spikes, FIX-B3-02 stays normal -> likely sensor fault.
    t1 = datetime(2026, 6, 14, 14, 32, 0, tzinfo=UTC)
    series["FF-R07"] += _spike_series("FF-R07", t1, peak_ppm=1180, duration_s=42, rng=rng)

    # Scenario 2 (historical, matches maintenance_log_ff_r07.md 2026-04-18 entry):
    # FF-R07 spikes, FIX-B3-01 stays normal -> likely sensor fault.
    t2 = datetime(2026, 4, 18, 9, 15, 0, tzinfo=UTC)
    series["FF-R07"] += _spike_series("FF-R07", t2, peak_ppm=860, duration_s=35, rng=rng)

    # Scenario 3 (new): both FF-R07 and FIX-B3-02 elevated -> likely real event.
    t3 = datetime(2026, 7, 8, 11, 5, 0, tzinfo=UTC)
    series["FF-R07"] += _spike_series("FF-R07", t3, peak_ppm=1400, duration_s=50, rng=rng)
    series["FIX-B3-02"] += _spike_series("FIX-B3-02", t3, peak_ppm=900, duration_s=50, rng=rng)

    # Scenario 4 (new): FF-R07 spikes but FIX-B3-02's reading for the window is stale
    # -> insufficient evidence (per SOP-014 Section 3, step 4). Removing FIX-B3-02's
    # regular baseline points near t4 creates a genuine data gap — otherwise the
    # periodic baseline series would still supply a "fresh" reading right through the
    # window and the staleness would never actually matter to a query.
    t4 = datetime(2026, 7, 10, 16, 40, 0, tzinfo=UTC)
    series["FF-R07"] += _spike_series("FF-R07", t4, peak_ppm=1050, duration_s=38, rng=rng)
    gap_start, gap_end = t4 - timedelta(hours=8), t4 + timedelta(hours=2)
    series["FIX-B3-02"] = [
        p
        for p in series["FIX-B3-02"]
        if not (gap_start <= datetime.fromisoformat(p["timestamp"]) <= gap_end)
    ]
    series["FIX-B3-02"] += _stale_series("FIX-B3-02", t4, last_good_value=9.5, hours_stale=6)

    for device_id in series:
        series[device_id].sort(key=lambda p: p["timestamp"])
    return series


ALERTS = [
    {
        "id": "alert-2026-06-14",
        "device_id": "FF-R07",
        "corroborating_device_id": "FIX-B3-02",
        "metric": "methane_ppm",
        "value": 1180,
        "window_seconds": 42,
        "triggered_at": "2026-06-14T14:32:21+00:00",
        "expected_classification": "likely_sensor_fault",
        "notes": "Flagship scenario; matches the Docs corpus inspection report.",
    },
    {
        "id": "alert-2026-04-18",
        "device_id": "FF-R07",
        "corroborating_device_id": "FIX-B3-01",
        "metric": "methane_ppm",
        "value": 860,
        "window_seconds": 35,
        "triggered_at": "2026-04-18T09:15:17+00:00",
        "expected_classification": "likely_sensor_fault",
        "notes": "Matches the maintenance log's 2026-04-18 entry.",
    },
    {
        "id": "alert-2026-07-08",
        "device_id": "FF-R07",
        "corroborating_device_id": "FIX-B3-02",
        "metric": "methane_ppm",
        "value": 1400,
        "window_seconds": 50,
        "triggered_at": "2026-07-08T11:05:25+00:00",
        "expected_classification": "likely_real_event",
        "notes": "Both devices elevated; new scenario not in the Docs corpus.",
    },
    {
        "id": "alert-2026-07-10",
        "device_id": "FF-R07",
        "corroborating_device_id": "FIX-B3-02",
        "metric": "methane_ppm",
        "value": 1050,
        "window_seconds": 38,
        "triggered_at": "2026-07-10T16:40:19+00:00",
        "expected_classification": "insufficient_evidence",
        "notes": "Corroborating sensor data is stale for this window.",
    },
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "devices.json").write_text(json.dumps(DEVICES, indent=2), encoding="utf-8", newline="\n")
    (OUT_DIR / "alerts.json").write_text(json.dumps(ALERTS, indent=2), encoding="utf-8", newline="\n")

    series = build_telemetry()
    for device_id, points in series.items():
        path = OUT_DIR / f"{device_id}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for point in points:
                f.write(json.dumps(point) + "\n")
        print(f"wrote {path} ({len(points)} points)")
    print(f"wrote {OUT_DIR / 'devices.json'} ({len(DEVICES)} devices)")
    print(f"wrote {OUT_DIR / 'alerts.json'} ({len(ALERTS)} scenarios)")


if __name__ == "__main__":
    main()
