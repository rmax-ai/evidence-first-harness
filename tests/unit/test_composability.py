"""Deterministic composability property fixtures and generated checks."""

from __future__ import annotations

from itertools import permutations
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

from evidence_first_harness.domain.composability import (
    COMPOSABILITY_CASE_ADAPTER,
    ComposabilityCase,
    ComposabilityVerifier,
    ExactStateEquivalenceOracle,
    ExternalOutcomeAction,
    ObservableState,
    UnknownExternalOutcomeCase,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "composability"
_CASE_LIST_ADAPTER = TypeAdapter(list[ComposabilityCase])
_EXPECTED_FAMILIES = {
    "temporal_cleanup",
    "partial_activation_cleanup",
    "dependency_reactivity",
    "reconciliation_idempotence",
    "convergence_permutation",
    "interruption_resume",
    "unknown_external_outcome_duplicate_prevention",
    "ownership_isolation",
}


def _load_cases(filename: str) -> list[ComposabilityCase]:
    return _CASE_LIST_ADAPTER.validate_json((_FIXTURE_DIR / filename).read_bytes())


def test_known_good_fixture_pair_passes_every_family() -> None:
    """Each canonical good fixture satisfies its semantic property."""
    cases = _load_cases("good.json")

    assert {case.family for case in cases} == _EXPECTED_FAMILIES
    assert all(ComposabilityVerifier().verify(case).passed for case in cases)


def test_known_bad_fixture_pair_fails_and_replays_every_family() -> None:
    """Each known-bad fixture fails and can be replayed from its evidence."""
    verifier = ComposabilityVerifier()
    cases = _load_cases("bad.json")

    assert {case.family for case in cases} == _EXPECTED_FAMILIES
    for case in cases:
        result = verifier.verify(case)
        assert not result.passed
        assert result.violation_codes
        assert result.counterexample_json is not None
        replay = COMPOSABILITY_CASE_ADAPTER.validate_json(result.counterexample_json)
        replay_result = verifier.verify(replay)
        assert not replay_result.passed
        assert replay_result.violation_codes


def test_transition_counterexamples_are_minimized_and_replayable() -> None:
    """Transition failures retain the smallest useful replay sequences."""
    verifier = ComposabilityVerifier()
    bad_cases = _load_cases("bad.json")

    partial = next(case for case in bad_cases if case.family == "partial_activation_cleanup")
    partial_result = verifier.verify(partial)
    assert partial_result.counterexample_json is not None
    partial_replay = COMPOSABILITY_CASE_ADAPTER.validate_json(partial_result.counterexample_json)
    assert partial_replay.family == "partial_activation_cleanup"
    assert len(partial_replay.events) == 2

    unknown = next(
        case for case in bad_cases if case.family == "unknown_external_outcome_duplicate_prevention"
    )
    unknown_result = verifier.verify(unknown)
    assert unknown_result.counterexample_json is not None
    unknown_replay = COMPOSABILITY_CASE_ADAPTER.validate_json(unknown_result.counterexample_json)
    assert isinstance(unknown_replay, UnknownExternalOutcomeCase)
    assert unknown_replay.steps == ("invoke", "outcome_unknown", "retry")


class _PermissiveNumericOracle:
    @staticmethod
    def equivalent(left: tuple[ObservableState, ...], right: tuple[ObservableState, ...]) -> bool:
        def normalize(states: tuple[ObservableState, ...]) -> tuple[tuple[str, str, str], ...]:
            normalized: list[tuple[str, str, str]] = []
            for state in states:
                try:
                    value = str(int(state.value))
                except ValueError:
                    value = state.value.strip()
                normalized.append((state.owner_id, state.state_id, value))
            return tuple(sorted(normalized))

        return normalize(left) == normalize(right)


def test_negative_control_rejects_a_permissive_normalization_oracle() -> None:
    """A normalizer that merges distinct opaque values fails calibration."""
    case = next(
        item for item in _load_cases("good.json") if item.family == "reconciliation_idempotence"
    )
    result = ComposabilityVerifier(_PermissiveNumericOracle()).verify(case)

    assert not result.passed
    assert result.violation_codes == ("oracle_negative_control_failed",)
    assert result.counterexample_json is not None
    assert '"kind":"oracle_negative_control"' in result.counterexample_json


def test_exact_oracle_ignores_order_but_not_value_normalization() -> None:
    """The default oracle ignores map order but preserves exact values."""
    first = ObservableState(
        state_id="setting",
        owner_id="worker",
        value="01",
        value_type="opaque",
    )
    second = ObservableState(
        state_id="another-setting",
        owner_id="worker",
        value="value",
        value_type="opaque",
    )
    oracle = ExactStateEquivalenceOracle()

    assert oracle.equivalent((first, second), (second, first))
    assert not oracle.equivalent(
        (first,),
        (first.model_copy(update={"value": "1"}),),
    )


def test_convergence_requires_the_complete_permutation_set() -> None:
    """Two matching orders cannot stand in for an exhaustive permutation check."""
    case = next(
        item for item in _load_cases("good.json") if item.family == "convergence_permutation"
    )
    incomplete_case = case.model_copy(update={"runs": case.runs[:1]})

    result = ComposabilityVerifier().verify(incomplete_case)

    assert not result.passed
    assert "permutations_not_exhaustive" in result.violation_codes


def test_boundary_model_rejects_unknown_fields_and_coercion() -> None:
    """Untrusted serialized observations reject extra keys and wrong types."""
    valid_case = _load_cases("good.json")[0].model_dump(mode="python")
    valid_case["unexpected"] = "not part of the contract"
    with pytest.raises(ValidationError):
        COMPOSABILITY_CASE_ADAPTER.validate_python(valid_case)

    wrong_type = _load_cases("good.json")[1].model_dump(mode="python")
    events = wrong_type["events"]
    first_event = {**events[0], "resource_id": 17}
    wrong_type["events"] = (first_event, *events[1:])
    with pytest.raises(ValidationError):
        COMPOSABILITY_CASE_ADAPTER.validate_python(wrong_type)


@given(interruption_index=st.integers(min_value=0, max_value=3))
def test_every_interruption_boundary_resumes_each_effect_once(
    interruption_index: int,
) -> None:
    """Generated interruption positions resume only effects not yet applied."""
    effects = ("reserve", "publish", "record")
    case = COMPOSABILITY_CASE_ADAPTER.validate_python(
        {
            "family": "interruption_resume",
            "claim_id": "generated-resume",
            "expected_effects": effects,
            "interruption_index": interruption_index,
            "applied_before_interruption": effects[:interruption_index],
            "resumed_effects": effects[interruption_index:],
            "terminal_effects": effects,
        }
    )

    assert ComposabilityVerifier().verify(case).passed


@given(operation_order=st.permutations(("set-a", "set-b", "set-c")))
def test_generated_operation_permutations_converge(
    operation_order: list[str],
) -> None:
    """Hypothesis-generated arrival orders share one observable terminal state."""
    operations = ("set-a", "set-b", "set-c")
    state = (
        ObservableState(
            state_id="desired",
            owner_id="worker",
            value="sha256:stable",
            value_type="digest",
        ),
    )
    case = COMPOSABILITY_CASE_ADAPTER.validate_python(
        {
            "family": "convergence_permutation",
            "claim_id": "generated-convergence",
            "expected_operations": operations,
            "runs": tuple(
                {"operation_order": order, "final_state": state}
                for order in permutations(operation_order)
            ),
        }
    )

    assert ComposabilityVerifier().verify(case).passed


_UNKNOWN_ACTIONS: tuple[ExternalOutcomeAction, ...] = (
    "invoke",
    "outcome_unknown",
    "observe_applied",
    "observe_absent",
    "confirmed_applied",
    "confirmed_absent",
    "retry",
)


@given(steps=st.lists(st.sampled_from(_UNKNOWN_ACTIONS), min_size=1, max_size=8))
def test_generated_unknown_outcome_traces_keep_replayable_counterexamples(
    steps: list[ExternalOutcomeAction],
) -> None:
    """Generated state-machine failures retain replayable counterexamples."""
    case = UnknownExternalOutcomeCase(
        family="unknown_external_outcome_duplicate_prevention",
        claim_id="generated-outcome",
        steps=tuple(steps),
    )
    verifier = ComposabilityVerifier()
    result = verifier.verify(case)

    if not result.passed:
        assert result.counterexample_json is not None
        replay = COMPOSABILITY_CASE_ADAPTER.validate_json(result.counterexample_json)
        assert not verifier.verify(replay).passed
