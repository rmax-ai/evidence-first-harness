# Evidence-First Harness

**Deterministic assurance system for AI-generated code.**

The Evidence-First Harness treats every AI-generated patch as an untrusted proposal.
It produces validated **Evidence Bundles** — claim-evidence-decision packages governed by explicit,
version-controlled policy — rather than accepting raw generated code.

## Principle

> No agent-generated change may be accepted unless every material claim introduced by
> the change is linked to sufficient, reproducible, risk-adjusted evidence.

## Status

**Alpha (Phase 6 complete).** 73 tests, 3 of 6 agents wired with real LLM calls,
17-node ADK workflow graph, 9 evidence executors, AST impact analysis,
mutation testing, adversarial review stubs, GitHub Check Runs integration.
Per-agent token tracking and USD cost reporting operational.

## Smoke Test (E2E — copy, paste, run)

```bash
# Clone and install
git clone https://github.com/rmax-ai/evidence-first-harness.git
cd evidence-first-harness
uv sync --extra dev

# Set API keys (only Anthropic + DeepSeek strictly required for 3 live agents)
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="sk-..."
# Optional: OPENAI_API_KEY, GEMINI_API_KEY (adversarial/independent review stubs only)

# Run the full evidence-first workflow on the harness repo itself
uv run efh run --repo .
```

You'll see the 17-node workflow with **real LLM calls, token counts, and USD costs**:

```
Evidence-First Harness — running on .

workflow_started               run_id=run_3da28c6662d9
worktree_created               base_commit=9007ebb1
repository_loaded              commit=9007ebb1

node_transition  start → load_repository
node_transition  load_repository → compile_specification
specification_agent_call  model=claude-opus-4-6  in=294  out=4096  cost_usd=0.311610
specification_compiled    artifact=art_e5ec1cf6  duration_ms=70276

node_transition  compile_specification → classify_initial_risk
node_transition  classify_initial_risk → validate_baseline
node_transition  validate_baseline → plan_implementation
planner_agent_call        model=claude-sonnet-5  in=430  out=770  cost_usd=0.012840
node_executed             plan_implementation    duration_ms=18995

node_transition  plan_implementation → generate_patch
implementation_agent_call model=deepseek-chat    in=276  out=34   cost_usd=0.000112
node_executed             generate_patch         duration_ms=1991

node_transition  generate_patch → analyze_impact
impact_analyzed  affected_tests=0 changed_files=20 confidence=0.2

node_transition  analyze_impact → reclassify_risk
node_transition  reclassify_risk → compile_evidence_plan
evidence_plan_compiled  check_count=5

node_transition  compile_evidence_plan → run_cheap_checks
evidence_executed  formatting  ruff     fail
evidence_executed  lint        ruff     fail
evidence_executed  type_check  pyright  fail
evidence_executed  secret_scan secrets  pass

node_transition  run_cheap_checks → run_behavioral_checks
evidence_executed  targeted_tests  pytest  fail

node_transition  run_behavioral_checks → run_adversarial_checks
adversarial_review_complete          # advisory stub (0 tokens)

node_transition  run_adversarial_checks → run_independent_review
independent_review_complete          # advisory stub (0 tokens)

node_transition  run_independent_review → assess_evidence_sufficiency
decision_rendered  decision=repair_required  mandatory_failed=4  passed=1  tier=3

workflow_ended  status=repair_required

Run ID: run_3da28c6662d9
Decision: repair_required
Repository: .
Base commit: 9007ebb1

│ Agent              Model                      In    Out Cost (USD) │
├──────────────────┼──────────────────────┼──────┼──────┼──────────┤
│ specification      claude-opus-4-6           294   4096 $ 0.311610 │
│ planner            claude-sonnet-5           430    770 $ 0.012840 │
│ implementation     deepseek-chat             276     34 $ 0.000112 │
├──────────────────┼──────────────────────┼──────┼──────┼──────────┤
│ TOTAL                                       1000   4900 $ 0.324562 │
```

**What happened:** The LLM agents (Opus 4.6 spec, Sonnet 5 planner, DeepSeek impl)
generated a patch proposal. Five deterministic evidence executors ran against it
(ruff, pyright, pytest, secret scan). The **deterministic decision engine** ruled
`repair_required` because 4/5 mandatory checks failed. Total cost: **$0.32**.
No LLM decided the outcome — only deterministic policy did.

## Agent Model Routing

| Agent | Model | Provider | Live? | Tokens² |
|-------|-------|----------|-------|--------|
| Specification | claude-opus-4-6 | Anthropic | ✅ Live | ~300/4096 |
| Planner | claude-sonnet-5 | Anthropic | ✅ Live | ~400/800 |
| Implementation | deepseek-chat | DeepSeek | ✅ Live | ~300/35 |
| Independent Test | claude-haiku-4-5 | Anthropic | ⬜ Stub | 0/0 |
| Adversarial Review | gemini-3.5-flash | Google | ⬜ Stub | 0/0 |
| Explanation | gemini-3.5-flash | Google | ⬜ Stub | 0/0 |

² Typical per-run. Stubs return static advisory JSON — no LLM cost incurred.

**Independence constraint:** Implementation model (DeepSeek) differs from all evaluator
models (Anthropic, Google). No model reviews its own output.

### Pricing (2026-07 USD per 1M tokens)

| Model | Input | Output |
|-------|------:|-------:|
| claude-opus-4-6 | $15.00 | $75.00 |
| claude-sonnet-5 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.80 | $4.00 |
| deepseek-chat | $0.27 | $1.10 |
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
uv run efh run --repo .         # Full E2E (~90s, needs API keys)
```

## License

MIT
