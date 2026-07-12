# Evidence-First Harness — Project Specification

> Ground truth for all implementation artifacts.
> Source: Telegram user specification, 2026-07-12.

## Core Invariant

No agent-generated change may be accepted unless every material claim introduced
by the change is linked to sufficient, reproducible, risk-adjusted evidence.

## Primary Output

An Evidence Bundle — not code. The bundle contains: interpreted specification,
proposed patch, affected system surface, risk classification, evidence plan,
verification results, adversarial evidence, known limitations, provenance records,
and a policy-derived decision.

## Agent Roles

1. **Specification Agent** — interpret task, derive requirements, identify invariants
2. **Implementation Planner Agent** — propose minimal plan, identify expected files
3. **Implementation Agent** — generate code in isolated worktree
4. **Independent Test Agent** — generate tests without seeing implementation reasoning
5. **Adversarial Review Agent** — identify unsupported claims, propose counterexamples
6. **Evidence Explanation Agent** — convert structured evidence to human-readable report

## Deterministic Services

- Repository manager, sandbox executor, policy engine, risk classifier
- AST dependency analyzer, test selector, evidence planner, evidence executors
- Evidence normalizer, sufficiency evaluator, provenance recorder, artifact store
- GitHub integration

## Evidence Tiers

| Tier | Required Evidence | Approval |
|------|------------------|----------|
| 3 | formatting, lint, type check, targeted tests, secret scan | Automated |
| 2 | + integration tests, security scan, mutation test | Code owner |
| 1 | + contract tests, dependency scan, performance, rollback | Code owner + security owner |

## Design Principles

1. Deterministic control, probabilistic reasoning
2. Evidence requirements precede implementation
3. Independent verification (reduce correlated failure)
4. Risk-adjusted assurance
5. Fail closed
6. Explicit uncertainty

## Research Question

Can a deterministic agent harness derive and execute a risk- and impact-adjusted
evidence plan that detects more defects and reduces human review burden compared
with conventional coding-agent workflows?

## Phases

1. Deterministic evidence runner (CLI, sandbox, executors, bundle, decision)
2. ADK implementation workflow (agents, graph, repair loop)
3. Impact-derived verification (AST, test selection, coverage)
4. Independent evidence (mutation, adversarial, benchmarks)
5. GitHub integration (issues, checks, PRs)
6. Research release (benchmark, analysis, paper, public)

## See Also

- Original specification (Telegram, 2026-07-12)
- `docs/architecture.md` — detailed architecture
- `docs/evidence-model.md` — evidence taxonomy
- `docs/threat-model.md` — security threat model
- `docs/policy-guide.md` — policy authoring guide
- `docs/research-protocol.md` — research methodology
