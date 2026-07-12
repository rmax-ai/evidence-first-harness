# Phase 4: Independent Evidence — Implementation Plan

> **For Hermes:** Wire existing components (mutation executor, agent stubs) into workflow.
> Minimal new code — mostly wiring and policy updates.

**Goal:** Wire mutation testing, adversarial review, and independent test generation into the ADK workflow graph so `efh run` exercises all evidence types for tiers 2+.

**Architecture:** Two new node handlers in nodes.py + dispatch wiring in session.py. Mutation executor already exists (Phase 1). Agent stubs exist (Phase 2). Focus on plumbing.

---

## Acceptance Criteria

- [ ] `handle_run_adversarial_checks` runs mutation executor against worktree, stores EvidenceRecord
- [ ] `handle_run_independent_review` produces structured advisory report artifact
- [ ] Session dispatch routes through adversarial_checks → independent_review nodes
- [ ] Policy already includes mutation_test in tier 2+ (verified)
- [ ] `efh run --repo .` includes adversarial_checks and independent_review nodes
- [ ] At least 4 new tests pass
- [ ] All 54 existing tests still pass

---

## Implementation Tasks

### Task 1: Add `handle_run_adversarial_checks` to nodes.py

Runs the MutationExecutor against the worktree. Collects surviving mutants, mutation score. Stores record in evidence_records list.

### Task 2: Add `handle_run_independent_review` to nodes.py

Creates a structured independent review artifact. Reads impact report + evidence records, compiles an advisory report with:
- Unsupported claims list
- Surviving mutations detail
- Evidence gaps
- Recommendation (advisory only)

### Task 3: Wire into session.py dispatch map

Replace `_return_success()` stubs with real handler calls.

### Task 4: Write tests

Tests for:
- Mutation executor integration (parses mutmut output, handles unavailable)
- Independent review handler produces structured output
- Node handlers return correct NodeStatus

### Task 5: E2E verification

`efh run --repo .` should show mutation_test executor attempting to run in adversarial_checks phase.
