# Composability verification

EFH models lifecycle properties as deterministic claims and plans them through
the existing evidence path. A claim is selected only when its declared
capability appears in `ImpactReport.affected_capabilities` and one of its
declared change shapes appears in `ImpactReport.change_shapes`. Selected
requirements are mandatory, deterministic evidence and reject on failure.
Unmatched claims do not run globally.

The semantic family names are language-neutral:

| Family | Claim |
|---|---|
| `temporal_cleanup` | Explicitly owned observable state is gone after removal. |
| `partial_activation_cleanup` | Resources acquired before activation failure are released, with no acquired side effects remaining. |
| `dependency_reactivity` | Dependents react within the declared propagation window and non-dependents remain unchanged. |
| `reconciliation_idempotence` | One and two reconciliations produce exactly equivalent observable state. |
| `convergence_permutation` | Concurrent operation permutations converge to the same observable state. |
| `interruption_resume` | Resume reaches the expected terminal effects without replaying applied effects. |
| `unknown_external_outcome_duplicate_prevention` | An unknown external outcome is observed or reconciled before retry; a harmful operation is never blindly retried. |
| `ownership_isolation` | Removal or reconciliation leaves state owned by other components unchanged. |

Claims can be attached to a compiled specification:

```python
ComposabilityClaim(
    id="worker-removal",
    family="temporal_cleanup",
    capability="worker",
    change_shapes=("removal",),
)
```

An impact report selects the claim by both dimensions:

```python
ImpactReport(
    affected_capabilities=("worker",),
    change_shapes=("removal",),
    confidence=1.0,
)
```

`ComposabilityExecutor` consumes JSON observations from a trusted
`ComposabilityCaseAdapter`. Adapters may call target-language tests through
bounded command tools, but must return the language-neutral case contract.
Pydantic validates the serialized boundary strictly. If no adapter is
configured, the executor returns unavailable evidence, so existing
fail-closed decision policy remains in control. Observed state values must be
opaque non-sensitive tokens or digests, not raw application data.

State comparisons are exact, with ordering ignored only for state-map entries.
Before using a state-equivalence oracle, the verifier checks a negative
control that distinguishes opaque values `"01"` and `"1"`. A permissive
numeric or whitespace normalizer fails this control. Failed transition cases
retain replayable JSON in `EvidenceRecord.counterexample`; activation and
unknown-outcome traces are delta-debugged while preserving their violation.
Convergence cases must include every operation permutation; the current
bounded contract supports groups of two through five operations.

Known-good and known-bad cases for all eight families live in
`tests/fixtures/composability/good.json` and `bad.json`. Tests also generate
operation permutations, interruption points, and unknown-outcome traces with
Hypothesis.
