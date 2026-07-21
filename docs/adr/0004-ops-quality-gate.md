# ADR 0004: Ops quality-gate policy, trace export, and deployment registry scope

- Status: Accepted
- Date: 2026-07-21

## Context

FieldForge Ops (milestone M5) needs to evaluate, trace, deploy, and monitor Docs,
Copilot, and Mesh. All three already produce real, measured evaluation reports
(`evals/reports/*.json`) and committed baselines (`evals/baselines/*.json`), and all
three already log structured JSON with a `trace_id` per request. Ops slice 1 builds
on that existing real data rather than inventing a parallel telemetry pipeline.

## Decisions

1. **Quality-gate thresholds are set now, from the baselines that already exist** —
   not left as `TBD`. The program brief says "do not invent thresholds before
   baseline evaluation is complete"; baseline evaluation *is* complete (three
   committed baseline files, each from a real run). The policy has two branches,
   because metrics don't all regress in the same direction:
   - **Rate/score metrics** (recall, accuracy, completion rate, ...): higher is
     better. A run **fails** if `current_value < baseline_value - 0.02` (absolute).
     The 0.02 tolerance exists so the gate doesn't flap on eval noise, not to hide
     real regressions — anything at 1.0 today still fails if it drops by more than
     two points.
   - **Latency metrics** (any metric name containing `latency`): lower is better. A
     run **fails** if `current_value > baseline_value * 1.5` (50% slower). This
     branch was added after a real bug found during slice-1 testing: the first
     version of `compute_gate` applied the higher-is-better rule to
     `latency_ms_p50` too, so a *faster* run (1.98ms vs. a 2.16ms baseline) was
     reported as a failing regression, because `1.98 < 2.16 - 0.02` is true even
     though faster is strictly better. Caught by running the real ingestion script
     against the real committed reports, not by unit tests written in advance —
     see `apps/ops_api/fieldforge_ops_api/gate.py::_is_lower_better` and
     `tests/unit/test_gate.py`.

   Metrics not present in the baseline are reported `missing`, not silently skipped.

2. **Trace export is a fire-and-forget HTTP call that can never break the calling
   service.** `fieldforge_observability.tracing.export_span()` POSTs a compact span
   record to Ops (`FIELDFORGE_OPS_TRACE_URL`, unset by default) with a short timeout,
   swallowing every exception. If Ops is down, the caller does not know or care —
   the same graceful-degradation posture as every other cross-service call in this
   suite (Docs' embedding adapter, Copilot's `retrieve_sop`, Mesh's delegation).
   Observability must never become a new availability dependency for the product
   being observed.

3. **The deployment registry is real bookkeeping, not real infrastructure.**
   `POST /deployments` creates a `Release` row and *enforces* that the linked
   `EvaluationRun` passed its quality gate — an actual constraint, not a formality —
   but "deploying" does not provision a container, call a cloud API, or move
   traffic. This is disclosed as a deployment *registry* throughout the docs, never
   described as a real deployment pipeline. Real infrastructure provisioning is a
   plausible M2 target once there's an actual staging environment to provision.

4. **The CI/CD regression demonstration is a test, not a GitHub Actions run.** The
   program brief calls the "prompt regression → gate fails → fix → gate passes →
   canary → rollback" sequence a primary portfolio feature. Reproducing it inside
   GitHub Actions would require actually breaking a product's code on a schedule,
   which is not something CI should do. Instead,
   `tests/integration/test_ops_regression_demo.py` drives the same sequence against
   real code: it ingests the real baseline, ingests a synthetically-regressed report
   (a copy of the real report with one metric lowered — not fabricated from
   nothing), shows the gate failing, ingests the original report again, shows the
   gate passing, creates a deployment, and rolls it back. Every step calls real Ops
   API code; only the "regression" input is constructed for the test, and it's
   clearly labeled as such.

## Consequences

- Positive: the quality gate has real numbers behind it from day one — no
  placeholder thresholds to forget about later.
- Positive: trace export is additive and safe to enable in any environment,
  including CI, without changing product behavior when Ops isn't running.
- Negative: "deployment" and "canary" are simulated bookkeeping in this slice — a
  reviewer must read the docs to know that, so it is stated in the README's
  Known Limitations section, not just here.
