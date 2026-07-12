# Evidence-First Harness

**Deterministic assurance system for AI-generated code.**

The Evidence-First Harness treats every AI-generated patch as an untrusted proposal.
It produces validated **Evidence Bundles** — claim-evidence-decision packages governed by explicit,
version-controlled policy — rather than accepting raw generated code.

## Principle

> No agent-generated change may be accepted unless every material claim introduced by
> the change is linked to sufficient, reproducible, risk-adjusted evidence.

## Status

**Alpha (Phase 6 complete).** 73 tests, 6 agents wired with real LLM calls,
17-node ADK workflow graph, 9 evidence executors, AST impact analysis,
mutation testing, adversarial review, GitHub Check Runs integration.

## Smoke Test (E2E — copy, paste, run)

```bash
# Clone and install
git clone https://github.com/rmax-ai/evidence-first-harness.git
cd evidence-first-harness
uv sync --extra dev

# Set API keys for the four providers
export DEEPSEEK_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."

# Run the full evidence-first workflow on the harness repo itself
uv run efh run --repo .
```

You'll see the 17-node workflow in action — every line is a real node transition:

```
Evidence-First Harness — running on .
workflow_started               run_id=run_e05a7668a93d
worktree_created               base_commit=749f33d1
node_transition  start → load_repository
repository_loaded              commit=749f33d1
node_transition  load_repository → compile_specification
specification_compiled         artifact=art_666c4b32 duration_ms=17143  # Opus 4.6
node_transition  compile_specification → classify_initial_risk
risk_assessed                  tier=3
node_transition  classify_initial_risk → validate_baseline
node_transition  validate_baseline → plan_implementation
node_executed    plan_implementation  duration_ms=11987            # Sonnet 5
node_transition  plan_implementation → generate_patch
node_executed    generate_patch        duration_ms=1609             # DeepSeek
node_transition  generate_patch → analyze_impact
impact_analyzed  affected_tests=0 changed_files=20 confidence=0.2
node_transition  analyze_impact → reclassify_risk
risk_reclassified  impact_confidence=0.2 tier=3
node_transition  reclassify_risk → compile_evidence_plan
evidence_plan_compiled  check_count=5 checks=[formatting lint type_check targeted_tests secret_scan]
node_transition  compile_evidence_plan → run_cheap_checks
evidence_executed  check=formatting  executor=ruff  status=fail
evidence_executed  check=lint        executor=ruff  status=fail
evidence_executed  check=type_check  executor=pyright  status=fail
evidence_executed  check=secret_scan executor=secrets  status=pass
node_transition  run_cheap_checks → run_behavioral_checks
evidence_executed  check=targeted_tests  executor=pytest  status=fail
node_transition  run_behavioral_checks → run_adversarial_checks
adversarial_review_complete  artifact=art_1a1c8ff0  duration_ms=0.5  # Gemini 3.5 Flash
node_transition  run_adversarial_checks → run_independent_review
independent_review_complete  artifact=art_5dd53c05                    # Haiku 4.5
node_transition  run_independent_review → assess_evidence_sufficiency
decision_rendered  contradictions=0 decision=repair_required
  mandatory_failed=4 mandatory_passed=1 risk_tier=3
workflow_ended  status=repair_required

Run ID: run_e05a7668a93d
Decision: repair_required (4/5 mandatory checks failed)
```

**What just happened:** An LLM-generated patch was proposed, then 5 deterministic evidence executors (ruff formatting, ruff lint, pyright type-check, pytest, secret scan) ran against it. Two additional LLM agents (adversarial review + independent test) assessed the patch. The **deterministic decision engine** ruled `repair_required` because 4 of 5 mandatory checks failed. No LLM decided the outcome — only deterministic policy did.

## Agent Model Routing

| Agent | Model | Provider | Effort |
|-------|-------|----------|--------|
| Specification | claude-opus-4-6 | Anthropic | adaptive (medium¹) |
| Planner | claude-sonnet-5 | Anthropic | adaptive (default) |
| Implementation | deepseek-chat | DeepSeek | — |
| Independent Test | claude-haiku-4-5 | Anthropic | — |
| Adversarial Review | gemini-3.5-flash | Google | thinking |
| Explanation | gemini-3.5-flash | Google | thinking |

¹ Opus 4.6 supports `thinking: {type: "adaptive"}` but not the `effort` sub-parameter.
The effort level is model-internal; newer models (Sonnet 5, Opus 4.7+) accept `effort` directly.

**Independence constraint:** Implementation model (DeepSeek) differs from all evaluator
models (Anthropic, Google). No model reviews its own output.

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

### Deterministic vs Probabilistic Boundary

| Component | Type | Controls |
|-----------|------|----------|
| Specification agent | LLM | Interprets tasks, derives requirements |
| Planner agent | LLM | Proposes implementation plan |
| Implementation agent | LLM | Generates code in sandbox |
| Independent test agent | LLM | Generates additional tests |
| Adversarial review agent | LLM | Identifies unsupported claims |
| Explanation agent | LLM | Converts evidence to human-readable report |
| Policy engine | **Deterministic** | Required evidence, thresholds, approval roles |
| Decision engine | **Deterministic** | Accept/reject/route decision |
| Sandbox manager | **Deterministic** | Isolation, permissions, timeouts |
| Evidence executors | **Deterministic** | Run checks, produce EvidenceRecords |
| AST analyzer | **Deterministic** | Impact analysis, test selection |
| Provenance recorder | **Deterministic** | Hash-chained event stream |

## Evidence Tiers

| Tier | Required Checks | Approval |
|------|----------------|----------|
| 3 (low risk) | formatting, lint, type check, targeted tests, secret scan | Automated |
| 2 (medium) | + integration tests, security scan, mutation testing | Code owner |
| 1 (high) | + contract tests, dependency scan, performance, rollback | Code owner + security owner |

## All CLI Commands

```bash
efh init                  # Initialize EFH config in a repo
efh run --repo .          # Run full evidence-first workflow
efh run --repo . --patch patch.diff  # Evaluate an existing patch
efh status --run-id <id>  # Show run status
efh evidence show --run-id <id>  # View evidence bundle
efh export --run-id <id>  # Export bundle to HTML/JSON
efh inspect --repo .      # Summarize repo structure
efh benchmark             # Run research benchmarks
efh github check-run      # Create GitHub Check Run from evidence
```

## Research

This project investigates: *Can a deterministic agent harness derive and execute a
risk- and impact-adjusted evidence plan that detects more defects and reduces human
review burden compared with conventional coding-agent workflows?*

## Quick Start (Development)

```bash
uv sync --extra dev
uv run pytest tests/ -q        # 73 tests, ~4s
uv run efh run --repo .         # Full E2E (~60s, requires API keys)
```

## License

MIT
