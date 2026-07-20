# FieldForge FF-R07 Mobile Inspection Robot — Operations Manual

## 1. Overview

The FF-R07 is a tracked mobile inspection robot used by FieldForge Industries for
routine environmental survey rounds, including methane leak detection along pipeline
corridors at Site B. It carries a methane sensor module, a stereo camera pair, and a
network radio for telemetry uplink.

## 2. Specifications

- Battery: 48V Li-ion, rated 6 hours continuous survey operation
- Methane sensor: catalytic bead type, range 0-5000 ppm, factory calibration interval 90 days
- Network: 5 GHz mesh radio, expected packet loss under normal conditions < 1%
- Operating temperature: -10C to 50C

## 3. Startup Procedure

1. Confirm battery charge above 20%.
2. Confirm methane sensor self-test passes (green LED).
3. Confirm network uplink established (radio LED solid, not blinking).
4. Dispatch robot to the assigned survey route.

## 4. Methane Sensor Module

The methane sensor module reports parts-per-million (ppm) readings once per second to
the fleet telemetry service. A sustained reading above 1000 ppm for more than 30
seconds triggers an automatic survey-stop and an alert to the operations queue. A
reading spike shorter than 30 seconds, or a spike that coincides with a sensor
self-diagnostic fault code, should be treated as a possible sensor fault rather than a
confirmed emissions event — see Section 6, Troubleshooting.

## 5. Robot Stop Conditions

The FF-R07 will automatically stop and hold position if any of the following occur:
- Methane reading exceeds 1000 ppm for more than 30 seconds
- Network uplink is lost for more than 60 seconds during an active survey
- Battery falls below 10% during an active survey
- A mechanical fault code is raised by the drive controller

## 6. Troubleshooting

### 6.1 Authorized troubleshooting steps (Operator or Engineer role)

The following steps may be performed without safety-manager approval, because they are
read-only or reversible and do not change the robot's physical state on site:
- Pull the robot's telemetry history for the stop window and compare against the
  fixed environmental sensor array reading for the same interval (see
  manual_ff_env_sensor_array.md, Section 4).
  IMPORTANT: if the fixed sensor array does not corroborate an elevated reading,
  treat the FF-R07 reading as a probable sensor fault, not a confirmed leak.
- Check the robot's self-diagnostic fault log for a methane-sensor fault code.
- Check network uplink packet-loss statistics for the stop window.
- Request a diagnostic report from the robot (does not move the robot or clear
  the hold state).

### 6.2 Actions that require Safety Manager approval

The following are state-changing and must not be performed without an approved
Approval Request per the FieldForge human-in-the-loop policy:
- Physically resuming the robot's survey route after a methane-triggered stop.
- Dispatching a technician to the robot's location.
- Restarting the methane sensor module firmware.
- Declaring the stop a false positive and clearing the incident without a
  corroborating fixed-sensor reading.

See sop_methane_survey_response.md for the full response procedure.
