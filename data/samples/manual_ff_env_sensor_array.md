# FieldForge Fixed Environmental Sensor Array — Operations Manual

## 1. Overview

The fixed environmental sensor array is a network of stationary sensors installed at
FieldForge Industries field sites, measuring methane concentration, temperature,
barometric pressure, and structural vibration. Unlike the FF-R07 mobile robot, fixed
sensors report continuously regardless of any survey route.

## 2. Specifications

- Methane sensor: infrared point type, range 0-10000 ppm, calibration interval 180 days
- Sampling interval: 10 seconds
- Network: wired backhaul with 5 GHz mesh fallback
- Battery backup: 24 hours on backhaul loss

## 3. Data Quality Flags

Each telemetry point is tagged with a data-quality flag: `ok`, `stale`, or
`suspect_fault`. A `suspect_fault` flag is raised automatically when a sensor's
reading changes faster than its rated response time allows, which typically
indicates a wiring or sensor-element fault rather than a real environmental event.

## 4. Using Fixed-Sensor Data to Corroborate Mobile Robot Readings

When a mobile inspection robot (e.g. FF-R07) reports an elevated methane reading, the
nearest fixed sensor's reading for the same time window should be checked before
treating the event as confirmed. Because the fixed sensor uses a different sensing
technology (infrared vs. catalytic bead) and a separate power/network path, agreement
between the two independently reduces the likelihood of a shared sensor fault
explaining both readings. Disagreement — mobile robot elevated, fixed sensor normal,
or vice versa — should be escalated as "insufficient evidence to confirm," not
resolved by picking one reading over the other.

## 5. Known False-Positive Patterns

- Intermittent network packet loss on a fixed sensor can cause its last-known-good
  reading to be reported as current (`stale` flag) long after conditions changed;
  a `stale`-flagged reading must not be used to corroborate or refute a robot alert.
- Sensors within 5 meters of a diesel generator have shown transient methane-adjacent
  readings during generator startup; check the site equipment log for generator
  activity before confirming an emissions event near a generator.
