# FieldForge Safety SOP-021: Inspection Robot Emergency Stop Response

## 1. Purpose

Defines the required response whenever an FF-series inspection robot automatically
stops mid-survey, for any trigger condition (methane, network loss, low battery,
mechanical fault).

## 2. Immediate Actions (no approval required)

- Confirm the robot is holding a safe position (not blocking a walkway or road).
- Pull the robot's stop-event log to identify the trigger condition.
- If the trigger was network loss or low battery, no further safety escalation is
  required; proceed directly to the maintenance workflow.
- If the trigger was a methane reading, follow SOP-014 (Methane Survey Alert Response)
  before taking any further action.
- If the trigger was a mechanical fault code, do not attempt remote diagnostics that
  would move the robot's drive system; request a diagnostic report only.

## 3. Escalation

Any robot stop lasting more than 4 hours without resolution must be escalated to the
Safety Manager regardless of trigger condition, since an unresolved stop represents an
unattended robot in the field.
