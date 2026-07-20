# Security Policy

This is a portfolio project, not a production service with real user data. There is no
paid bug bounty. That said, the guardrail and threat-model work is meant to be taken
seriously as engineering, and reports are welcome.

## Reporting

Open a GitHub issue describing the concern. For anything involving an actual exploit
against a deployed instance of this project (there isn't one publicly hosted as of
slice 1), do not include exploit details in a public issue — open an issue asking for
a private contact method instead.

## Scope

- In scope: the code in this repository (services/, apps/, packages/).
- Out of scope: third-party dependencies (report upstream), the synthetic data itself
  (it's fictional by design — see [DATA_CARD.md](DATA_CARD.md)).

## What's already covered

See [docs/threat-model/THREAT_MODEL.md](docs/threat-model/THREAT_MODEL.md) for the
current threat model and which mitigations are implemented vs. planned, and
[evals/datasets/guardrails_docs_v1.jsonl](evals/datasets/guardrails_docs_v1.jsonl) for
the adversarial test cases that back it.
