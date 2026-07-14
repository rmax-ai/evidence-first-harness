# Evidence-First Harness

**Deterministic assurance system for AI-generated code.**

The Evidence-First Harness treats every AI-generated patch as an untrusted proposal.
It produces validated **Evidence Bundles** — claim-evidence-decision packages governed by explicit,
version-controlled policy — rather than accepting raw generated code.

## Principle

> No agent-generated change may be accepted unless every material claim introduced by
> the change is linked to sufficient, reproducible, risk-adjusted evidence.

## Status

**Alpha (Phase 6 complete).** 85 tests, 3 of 6 agents wired with real LLM calls,
17-node ADK workflow graph, 9 evidence executors, AST impact analysis,
mutation testing, adversarial review stubs, GitHub Check Runs integration.
Per-agent token tracking and USD cost reporting operational.

## Smoke Test (E2E — copy, paste, run)

```bash
# Clone and install
git clone https://github.com/rmax-ai/evidence-first-harness.git
cd evidence-first-harness
uv sync --extra dev

# Set API keys (Anthropic + OpenAI are required for the three live agents)
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
# Optional: GEMINI_API_KEY (adversarial/independent review stubs only)

# Run the full evidence-first workflow on the harness repo itself
uv run efh run --repo . --task "Add a focused test for the policy engine."
```

You'll see the 17-node workflow with **real LLM calls, token counts, and USD costs**:

```
Evidence-First Harness — running on .

workflow_started               run_id=run_c6ec67e305e0
worktree_created               base_commit=233ebbac
repository_loaded              commit=233ebbac repository_context=art_bf38f7dd96a6ae47

node_transition  start → load_repository
node_transition  load_repository → compile_specification
specification_agent_call  model=claude-sonnet-5  in=13570  out=4096  cost_usd=0.102150
specification_compiled    artifact=art_0afbe956c8b24d1d duration_ms=49756

node_transition  compile_specification → classify_initial_risk
node_transition  classify_initial_risk → validate_baseline
node_transition  validate_baseline → plan_implementation
planner_agent_call        model=claude-opus-4-6  in=11871  out=2015  cost_usd=0.329190
node_executed             plan_implementation    duration_ms=42945

node_transition  plan_implementation → generate_patch
implementation_agent_call model=gpt-5.6-terra   in=11393  out=3007 cost_usd=0.073588
node_executed             generate_patch         duration_ms=21796

node_transition  generate_patch → analyze_impact
impact_analyzed  affected_tests=1 changed_files=2 confidence=0.2

node_transition  analyze_impact → reclassify_risk
node_transition  reclassify_risk → compile_evidence_plan
evidence_plan_compiled  check_count=5

node_transition  compile_evidence_plan → run_cheap_checks
evidence_executed  formatting  ruff     fail
evidence_executed  lint        ruff     fail
evidence_executed  type_check  pyright  fail
evidence_executed  secret_scan secrets  fail

node_transition  run_cheap_checks → run_behavioral_checks
evidence_executed  targeted_tests  pytest  pass

node_transition  run_behavioral_checks → run_adversarial_checks
adversarial_review_complete          # advisory stub (0 tokens)

node_transition  run_adversarial_checks → run_independent_review
independent_review_complete          # advisory stub (0 tokens)

node_transition  run_independent_review → assess_evidence_sufficiency
decision_rendered  decision=repair_required  mandatory_failed=4  passed=1  tier=3

workflow_ended  status=repair_required

Run ID: run_c6ec67e305e0
Decision: repair_required
Repository: .
Base commit: 233ebbac

│ Agent              Model                      In    Out Cost (USD) │
├──────────────────┼──────────────────────┼──────┼──────┼──────────┤
│ specification      claude-sonnet-5         13570   4096 $ 0.102150 │
│ planner            claude-opus-4-6         11871   2015 $ 0.329190 │
│ implementation     gpt-5.6-terra           11393   3007 $ 0.073588 │
├──────────────────┼──────────────────────┼──────┼──────┼──────────┤
│ TOTAL                                      36834   9118 $ 0.504927 │
```

**What happened:** This recorded run generated and applied a structured two-file patch in an
isolated worktree. Targeted tests passed, but formatting, lint, type checking, and secret scanning
failed. The **deterministic decision engine** therefore returned `repair_required` (4/5 mandatory
checks failed) and removed the worktree. Total recorded cost: **$0.504927**. No LLM decided the
outcome — only deterministic policy did.

## Agent Model Routing

| Agent | Model | Provider | Live? | Tokens² |
|-------|-------|----------|-------|--------|
| Specification | claude-sonnet-5 | Anthropic | ✅ Live | 13570/4096 |
| Planner | claude-opus-4-6 | Anthropic | ✅ Live | 11871/2015 |
| Implementation | gpt-5.6-terra | OpenAI | ✅ Live | 11393/3007 |
| Independent Test | claude-haiku-4-5 | Anthropic | ⬜ Stub | 0/0 |
| Adversarial Review | gemini-3.5-flash | Google | ⬜ Stub | 0/0 |
| Explanation | gemini-3.5-flash | Google | ⬜ Stub | 0/0 |

² Recorded in `run_c6ec67e305e0`. Stubs return static advisory JSON — no LLM cost incurred.

**Independence constraint:** Implementation model (OpenAI) differs from all evaluator
models (Anthropic, Google). No model reviews its own output.

### Pricing (2026-07 USD per 1M tokens)

| Model | Input | Output |
|-------|------:|-------:|
| claude-opus-4-6 | $15.00 | $75.00 |
| claude-sonnet-5 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.80 | $4.00 |
| gpt-5.6-terra | $2.50 | $15.00 |
| gemini-3.5-flash | $0.075 | $0.30 |

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
| Implementation agent | LLM | Proposes a structured patch; harness validates and applies it in the sandbox |
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
efh run --repo . --task "Describe the requested code change"  # Run workflow
efh run --repo . --spec task.yaml  # Run a YAML task specification
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
uv run pytest tests/ -q        # 85 tests, ~7s
uv run efh run --repo . --task "Describe the requested code change"  # Full E2E
```

## License

MIT
