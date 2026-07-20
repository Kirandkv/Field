# FieldForge Safety SOP-014: Methane Survey Alert Response

Version: 3 (supersedes Version 2, dated prior to the fixed-sensor corroboration
requirement in Section 3 below)

## 1. Purpose

Defines the required response when a mobile inspection robot or fixed sensor reports
an elevated methane reading during a survey.

## 2. Scope

Applies to all FieldForge Industries field sites operating FF-series inspection robots
and fixed environmental sensor arrays.

## 3. Procedure

1. On receipt of a methane alert, an Operator or Engineer must pull telemetry for the
   alerting device and the nearest corroborating device (mobile-to-fixed or
   fixed-to-fixed) for the same time window. This corroboration step is mandatory as
   of Version 3 and may not be skipped, including for high-confidence-looking spikes.
2. If both devices show elevated readings: classify as a likely real emissions event.
   Escalate immediately to the Safety Manager. Do not dispatch personnel to the area
   without Safety Manager sign-off.
3. If only one device shows an elevated reading and the other is normal (not stale,
   not faulted): classify as a likely sensor fault. Do not clear the incident without
   Safety Manager approval, but personnel are not restricted from the area.
4. If the corroborating device's data is stale, faulted, or unavailable: classify as
   insufficient evidence. Do not classify as either a confirmed event or a false
   positive. Request additional evidence (extended telemetry window, second sensor)
   before making a determination.
5. Resuming a stopped robot's survey route requires Safety Manager approval in all
   cases, regardless of the classification in steps 2-4.

## 4. Approval Requirements Summary

| Action | Approval required |
|---|---|
| Pulling telemetry / diagnostic history | No |
| Classifying an alert as likely fault vs. likely event | No (documented judgment call, logged) |
| Declaring an incident resolved / false positive | Yes — Safety Manager |
| Resuming robot survey route | Yes — Safety Manager |
| Dispatching a technician to site | Yes — Safety Manager |
