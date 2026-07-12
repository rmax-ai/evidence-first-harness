# Evidence-First Harness

**Deterministic assurance system for AI-generated code.**

The Evidence-First Harness treats every AI-generated patch as an untrusted proposal.
It produces validated **Evidence Bundles** — claim-evidence-decision packages governed by explicit,
version-controlled policy — rather than accepting raw generated code.

## Principle

> No agent-generated change may be accepted unless every material claim introduced by
> the change is linked to sufficient, reproducible, risk-adjusted evidence.

## Status

**Pre-alpha.** Phase 1 (deterministic evidence runner) under active development.

## Quick Start

```bash
# Install
uv sync
uv sync --extra dev

# Initialize a harness config in your repo
efh init

# Evaluate an existing patch
efh run-existing-patch --repo . --patch patch.diff

# View evidence
efh evidence show --run-id run_01J
```

## Architecture

```
Task/Issue → Spec Compilation → Risk Classification → Baseline Validation
→ Candidate Implementation (ADK agent) → Patch Normalization
→ Impact Analysis → Risk Reclassification → Evidence Plan
→ Deterministic Checks → Behavioral Checks → Adversarial Checks
→ Independent Review → Evidence Sufficiency → Decision → Evidence Bundle
```

The LLM agents (spec, planner, implementer, independent test, adversarial review, explanation)
are contained within a deterministic ADK graph workflow. Policy, sandbox permissions,
acceptance thresholds, and the final decision are all implemented in deterministic Python code.

## Evidence Tiers

| Tier | Required Checks | Approval |
|------|----------------|----------|
| 3 (low risk) | formatting, lint, type check, targeted tests, secret scan | Automated |
| 2 (medium) | + integration tests, security scan, mutation testing | Code owner |
| 1 (high) | + contract tests, dependency scan, performance, rollback | Code owner + security owner |

## Research

This project investigates: *Can a deterministic agent harness derive and execute a
risk- and impact-adjusted evidence plan that detects more defects and reduces human
review burden compared with conventional coding-agent workflows?*

## License

MIT
