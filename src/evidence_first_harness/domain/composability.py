"""Language-neutral composability claims and deterministic verification rules."""

from __future__ import annotations

import json
from collections.abc import Callable
from itertools import permutations
from math import ceil
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, Field, TypeAdapter, model_validator

ComposabilityFamily = Literal[
    "temporal_cleanup",
    "partial_activation_cleanup",
    "dependency_reactivity",
    "reconciliation_idempotence",
    "convergence_permutation",
    "interruption_resume",
    "unknown_external_outcome_duplicate_prevention",
    "ownership_isolation",
]
ChangeShape = Literal[
    "activation",
    "removal",
    "dependency_change",
    "reconciliation",
    "concurrent_operations",
    "interruption",
    "unknown_external_outcome",
    "ownership_change",
]
ExternalOutcomeAction = Literal[
    "invoke",
    "outcome_unknown",
    "observe_applied",
    "observe_absent",
    "confirmed_applied",
    "confirmed_absent",
    "retry",
]
_ALLOWED_CHANGE_SHAPES: dict[ComposabilityFamily, frozenset[ChangeShape]] = {
    "temporal_cleanup": frozenset({"removal"}),
    "partial_activation_cleanup": frozenset({"activation"}),
    "dependency_reactivity": frozenset({"dependency_change"}),
    "reconciliation_idempotence": frozenset({"reconciliation"}),
    "convergence_permutation": frozenset({"concurrent_operations"}),
    "interruption_resume": frozenset({"interruption"}),
    "unknown_external_outcome_duplicate_prevention": frozenset({"unknown_external_outcome"}),
    "ownership_isolation": frozenset({"removal", "reconciliation", "ownership_change"}),
}


class _ClosedModel(BaseModel):
    """Shared strict, immutable boundary for composability data."""

    model_config = {"extra": "forbid", "frozen": True, "strict": True}


class ComposabilityClaim(_ClosedModel):
    """A property claim linked to one affected capability and change shape."""

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$", max_length=80)
    family: ComposabilityFamily
    capability: str = Field(..., min_length=1, max_length=128)
    change_shapes: tuple[ChangeShape, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_change_shapes(self) -> Self:
        """Reject duplicate or family-incompatible change shapes."""
        if len(set(self.change_shapes)) != len(self.change_shapes):
            raise ValueError("change_shapes must be unique")
        if not set(self.change_shapes) <= _ALLOWED_CHANGE_SHAPES[self.family]:
            raise ValueError("change_shapes are incompatible with the property family")
        return self


class _ComposabilityCase(_ClosedModel):
    claim_id: str = Field(..., pattern=r"^[a-z0-9_-]+$", max_length=80)


class OwnedState(_ClosedModel):
    """An observable state identifier and its explicit owner."""

    state_id: str = Field(..., min_length=1, max_length=256)
    component_id: str = Field(..., min_length=1, max_length=128)


class ObservableState(_ClosedModel):
    """A scoped state value represented by a non-sensitive token or digest."""

    state_id: str = Field(..., min_length=1, max_length=256)
    owner_id: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., max_length=512)
    value_type: Literal["opaque", "digest"] = "opaque"


class TemporalCleanupCase(_ComposabilityCase):
    """Only explicitly owned state is observed for temporal cleanup."""

    family: Literal["temporal_cleanup"]
    component_id: str = Field(..., min_length=1, max_length=128)
    explicitly_owned_state: tuple[OwnedState, ...] = Field(..., min_length=1)
    state_after_removal: tuple[OwnedState, ...] = ()


class ActivationEvent(_ClosedModel):
    """One resource event in a partial activation trace."""

    action: Literal["acquire", "activation_failed", "release"]
    resource_id: str | None = None

    @model_validator(mode="after")
    def validate_resource_reference(self) -> Self:
        """Require resource identifiers only on acquire and release events."""
        if self.action == "activation_failed":
            if self.resource_id is not None:
                raise ValueError("activation_failed must not name a resource")
        elif self.resource_id is None or not self.resource_id:
            raise ValueError("acquire and release events require a resource_id")
        return self


class PartialActivationCleanupCase(_ComposabilityCase):
    """Resources acquired during a failed activation and the resulting trace."""

    family: Literal["partial_activation_cleanup"]
    events: tuple[ActivationEvent, ...] = Field(..., min_length=1)
    remaining_resources: tuple[str, ...] = ()


class DependentObservation(_ClosedModel):
    """Expected and observed reaction of a dependent component."""

    component_id: str = Field(..., min_length=1, max_length=128)
    dependency_ids: tuple[str, ...] = Field(..., min_length=1)
    value_before: str
    expected_value: str
    observed_value: str
    observed_after_ms: int = Field(..., ge=0)


class NonDependentObservation(_ClosedModel):
    """Before and after values for an unaffected component."""

    component_id: str = Field(..., min_length=1, max_length=128)
    dependency_ids: tuple[str, ...] = ()
    value_before: str
    observed_value: str


class DependencyReactivityCase(_ComposabilityCase):
    """A dependency change, its propagation window, and scoped observations."""

    family: Literal["dependency_reactivity"]
    changed_dependency_id: str = Field(..., min_length=1, max_length=128)
    dependency_value_before: str
    dependency_value_after: str
    propagation_window_ms: int = Field(..., ge=0)
    dependent_observations: tuple[DependentObservation, ...] = Field(..., min_length=1)
    non_dependent_observations: tuple[NonDependentObservation, ...] = Field(..., min_length=1)


class ReconciliationIdempotenceCase(_ComposabilityCase):
    """Observable state after one and two applications of reconciliation."""

    family: Literal["reconciliation_idempotence"]
    state_after_once: tuple[ObservableState, ...] = Field(..., min_length=1)
    state_after_twice: tuple[ObservableState, ...] = Field(..., min_length=1)


class PermutationRun(_ClosedModel):
    """One operation arrival order and its observable terminal state."""

    operation_order: tuple[str, ...] = Field(..., min_length=2, max_length=5)
    final_state: tuple[ObservableState, ...] = Field(..., min_length=1)


class ConvergencePermutationCase(_ComposabilityCase):
    """Final states observed for two or more arrival orders of one operation set."""

    family: Literal["convergence_permutation"]
    expected_operations: tuple[str, ...] = Field(..., min_length=2, max_length=5)
    runs: tuple[PermutationRun, ...] = Field(..., min_length=2, max_length=120)


class InterruptionResumeCase(_ComposabilityCase):
    """Effects applied before and after interruption and the terminal state."""

    family: Literal["interruption_resume"]
    expected_effects: tuple[str, ...] = Field(..., min_length=1)
    interruption_index: int = Field(..., ge=0)
    applied_before_interruption: tuple[str, ...] = ()
    resumed_effects: tuple[str, ...] = ()
    terminal_effects: tuple[str, ...] = Field(..., min_length=1)


class UnknownExternalOutcomeCase(_ComposabilityCase):
    """A state-machine trace for a potentially harmful external operation."""

    family: Literal["unknown_external_outcome_duplicate_prevention"]
    steps: tuple[ExternalOutcomeAction, ...] = Field(..., min_length=1)


class OwnershipIsolationCase(_ComposabilityCase):
    """State not owned by the component before and after its scoped operation."""

    family: Literal["ownership_isolation"]
    component_id: str = Field(..., min_length=1, max_length=128)
    operation: Literal["removal", "reconciliation"]
    state_before: tuple[ObservableState, ...] = Field(..., min_length=1)
    state_after: tuple[ObservableState, ...] = ()


type ComposabilityCase = Annotated[
    TemporalCleanupCase
    | PartialActivationCleanupCase
    | DependencyReactivityCase
    | ReconciliationIdempotenceCase
    | ConvergencePermutationCase
    | InterruptionResumeCase
    | UnknownExternalOutcomeCase
    | OwnershipIsolationCase,
    Field(discriminator="family"),
]
COMPOSABILITY_CASE_ADAPTER: TypeAdapter[ComposabilityCase] = TypeAdapter(ComposabilityCase)


class ComposabilityVerification(_ClosedModel):
    """Deterministic result for one composability case."""

    claim_id: str
    family: ComposabilityFamily
    passed: bool
    violation_codes: tuple[str, ...] = ()
    counterexample_json: str | None = None


class StateEquivalenceOracle(Protocol):
    """Exact-by-default comparison boundary for observable state projections."""

    def equivalent(
        self, left: tuple[ObservableState, ...], right: tuple[ObservableState, ...]
    ) -> bool:
        """Return whether two explicit observable-state projections match."""
        ...


class ExactStateEquivalenceOracle:
    """Compare scoped state without value normalization or ownership filtering."""

    @staticmethod
    def equivalent(left: tuple[ObservableState, ...], right: tuple[ObservableState, ...]) -> bool:
        """Compare all owner, identifier, type, and value fields exactly."""

        def order_key(item: ObservableState) -> tuple[str, str]:
            return item.owner_id, item.state_id

        return tuple(sorted(left, key=order_key)) == tuple(sorted(right, key=order_key))


_ORACLE_CONTROL_LEFT = (
    ObservableState(
        state_id="oracle-control",
        owner_id="control",
        value="01",
        value_type="opaque",
    ),
)
_ORACLE_CONTROL_RIGHT = (
    ObservableState(
        state_id="oracle-control",
        owner_id="control",
        value="1",
        value_type="opaque",
    ),
)


class ComposabilityVerifier:
    """Evaluate language-neutral lifecycle properties without probabilistic judging."""

    def __init__(self, state_oracle: StateEquivalenceOracle | None = None) -> None:
        self._state_oracle = state_oracle or ExactStateEquivalenceOracle()

    def verify(self, case: ComposabilityCase) -> ComposabilityVerification:
        """Verify one typed observation and retain a replayable failure input."""
        if self._requires_state_oracle(case):
            try:
                oracle_accepted_control = self._state_oracle.equivalent(
                    _ORACLE_CONTROL_LEFT, _ORACLE_CONTROL_RIGHT
                )
            except Exception:
                oracle_accepted_control = True
            if oracle_accepted_control:
                return ComposabilityVerification(
                    claim_id=case.claim_id,
                    family=case.family,
                    passed=False,
                    violation_codes=("oracle_negative_control_failed",),
                    counterexample_json=_oracle_control_json(),
                )

        violations = self._evaluate(case)
        if not violations:
            return ComposabilityVerification(
                claim_id=case.claim_id,
                family=case.family,
                passed=True,
            )

        codes = tuple(dict.fromkeys(violations))
        return ComposabilityVerification(
            claim_id=case.claim_id,
            family=case.family,
            passed=False,
            violation_codes=codes,
            counterexample_json=self._counterexample(case, codes),
        )

    @staticmethod
    def _requires_state_oracle(case: ComposabilityCase) -> bool:
        return isinstance(
            case,
            (
                ReconciliationIdempotenceCase,
                ConvergencePermutationCase,
                OwnershipIsolationCase,
            ),
        )

    def _evaluate(self, case: ComposabilityCase) -> tuple[str, ...]:
        if isinstance(case, TemporalCleanupCase):
            return _verify_temporal_cleanup(case)
        if isinstance(case, PartialActivationCleanupCase):
            return _verify_partial_activation(case.events, case.remaining_resources)
        if isinstance(case, DependencyReactivityCase):
            return _verify_dependency_reactivity(case)
        if isinstance(case, ReconciliationIdempotenceCase):
            return _verify_reconciliation(case, self._state_oracle)
        if isinstance(case, ConvergencePermutationCase):
            return _verify_convergence(case, self._state_oracle)
        if isinstance(case, InterruptionResumeCase):
            return _verify_interruption_resume(case)
        if isinstance(case, UnknownExternalOutcomeCase):
            return _verify_unknown_outcome(case.steps)
        return _verify_ownership_isolation(case, self._state_oracle)

    def _counterexample(self, case: ComposabilityCase, violation_codes: tuple[str, ...]) -> str:
        if isinstance(case, PartialActivationCleanupCase) and (
            "resources_not_released" in violation_codes
        ):
            events = _minimize_sequence(
                case.events,
                lambda candidate: (
                    "resources_not_released"
                    in _verify_partial_activation(candidate, case.remaining_resources)
                ),
            )
            return case.model_copy(update={"events": events}).model_dump_json()
        if isinstance(case, UnknownExternalOutcomeCase) and (
            "blind_retry_after_unknown" in violation_codes
        ):

            def preserves_blind_retry(candidate: tuple[ExternalOutcomeAction, ...]) -> bool:
                """Retain the first blind retry violation during shrinking."""
                return "blind_retry_after_unknown" in _verify_unknown_outcome(candidate)

            steps = _minimize_sequence(
                case.steps,
                preserves_blind_retry,
            )
            return case.model_copy(update={"steps": steps}).model_dump_json()
        if isinstance(case, InterruptionResumeCase) and "effect_replayed" in violation_codes:
            replay = (*case.applied_before_interruption, *case.resumed_effects)
            duplicate = _first_duplicate(replay)
            if duplicate is not None:
                minimized = case.model_copy(
                    update={
                        "expected_effects": (duplicate,),
                        "interruption_index": 1,
                        "applied_before_interruption": (duplicate,),
                        "resumed_effects": (duplicate,),
                        "terminal_effects": (duplicate,),
                    }
                )
                return minimized.model_dump_json()
        return case.model_dump_json()


def _verify_temporal_cleanup(case: TemporalCleanupCase) -> tuple[str, ...]:
    violations: list[str] = []
    owned_pairs = {(state.component_id, state.state_id) for state in case.explicitly_owned_state}
    if any(state.component_id != case.component_id for state in case.explicitly_owned_state):
        violations.append("ownership_scope_mismatch")
    if len(owned_pairs) != len(case.explicitly_owned_state):
        violations.append("duplicate_owned_state")
    remaining_pairs = {(state.component_id, state.state_id) for state in case.state_after_removal}
    if len(remaining_pairs) != len(case.state_after_removal):
        violations.append("duplicate_observed_state")
    if owned_pairs & remaining_pairs:
        violations.append("owned_state_survived_removal")
    return tuple(violations)


def _verify_partial_activation(
    events: tuple[ActivationEvent, ...], remaining_resources: tuple[str, ...]
) -> tuple[str, ...]:
    violations: list[str] = []
    failure_positions = [
        index for index, event in enumerate(events) if event.action == "activation_failed"
    ]
    if len(failure_positions) != 1:
        return ("activation_failure_missing_or_ambiguous",)

    failure_index = failure_positions[0]
    active_resources: set[str] = set()
    acquired_resources: set[str] = set()
    for index, event in enumerate(events):
        if event.action == "activation_failed":
            continue
        resource_id = event.resource_id
        if resource_id is None:
            continue
        if index < failure_index:
            if event.action == "acquire":
                if resource_id in acquired_resources:
                    violations.append("duplicate_resource_acquisition")
                else:
                    acquired_resources.add(resource_id)
                    active_resources.add(resource_id)
            elif resource_id not in active_resources:
                violations.append("release_without_acquisition")
            else:
                active_resources.remove(resource_id)
        elif event.action != "release":
            violations.append("side_effect_after_activation_failure")
        elif resource_id not in active_resources:
            violations.append("release_without_acquisition")
        else:
            active_resources.remove(resource_id)

    remaining_set = set(remaining_resources)
    if len(remaining_set) != len(remaining_resources):
        violations.append("duplicate_remaining_resource")
    if remaining_set != active_resources:
        violations.append("remaining_resources_mismatch")
    if active_resources:
        violations.append("resources_not_released")
    if remaining_set:
        violations.append("partial_side_effect_survived")
    return tuple(violations)


def _verify_dependency_reactivity(case: DependencyReactivityCase) -> tuple[str, ...]:
    violations: list[str] = []
    if case.dependency_value_before == case.dependency_value_after:
        violations.append("dependency_change_not_exercised")
    for observation in case.dependent_observations:
        if case.changed_dependency_id not in observation.dependency_ids:
            violations.append("dependent_not_linked_to_changed_dependency")
        if observation.observed_after_ms > case.propagation_window_ms:
            violations.append("dependent_reaction_outside_propagation_window")
        if observation.observed_value != observation.expected_value:
            violations.append("dependent_reaction_incorrect")
    for observation in case.non_dependent_observations:
        if case.changed_dependency_id in observation.dependency_ids:
            violations.append("non_dependent_declares_changed_dependency")
        if observation.observed_value != observation.value_before:
            violations.append("non_dependent_was_affected")
    return tuple(violations)


def _has_duplicate_state_keys(states: tuple[ObservableState, ...]) -> bool:
    keys = [(state.owner_id, state.state_id) for state in states]
    return len(keys) != len(set(keys))


def _verify_reconciliation(
    case: ReconciliationIdempotenceCase, oracle: StateEquivalenceOracle
) -> tuple[str, ...]:
    violations: list[str] = []
    if _has_duplicate_state_keys(case.state_after_once) or _has_duplicate_state_keys(
        case.state_after_twice
    ):
        violations.append("duplicate_observable_state")
    if not oracle.equivalent(case.state_after_once, case.state_after_twice):
        violations.append("reconciliation_not_idempotent")
    return tuple(violations)


def _verify_convergence(
    case: ConvergencePermutationCase, oracle: StateEquivalenceOracle
) -> tuple[str, ...]:
    violations: list[str] = []
    expected_operations = set(case.expected_operations)
    if len(expected_operations) != len(case.expected_operations):
        violations.append("expected_operations_not_unique")

    valid_orders: list[tuple[str, ...]] = []
    for run in case.runs:
        if (
            len(run.operation_order) != len(expected_operations)
            or set(run.operation_order) != expected_operations
        ):
            violations.append("operation_order_not_permutation")
        else:
            valid_orders.append(run.operation_order)
        if _has_duplicate_state_keys(run.final_state):
            violations.append("duplicate_observable_state")

    if len(set(valid_orders)) != len(valid_orders):
        violations.append("duplicate_permutation_run")
    if len(expected_operations) == len(case.expected_operations):
        expected_permutations = set(permutations(case.expected_operations))
        if (
            len(valid_orders) != len(expected_permutations)
            or set(valid_orders) != expected_permutations
        ):
            violations.append("permutations_not_exhaustive")
    first_state = case.runs[0].final_state
    if any(not oracle.equivalent(first_state, run.final_state) for run in case.runs[1:]):
        violations.append("permutation_nonconvergence")
    return tuple(violations)


def _first_duplicate(values: tuple[str, ...]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def _verify_interruption_resume(case: InterruptionResumeCase) -> tuple[str, ...]:
    violations: list[str] = []
    if len(set(case.expected_effects)) != len(case.expected_effects):
        violations.append("expected_effects_not_unique")
    if case.interruption_index > len(case.expected_effects):
        violations.append("interruption_index_out_of_range")
        return tuple(violations)

    expected_prefix = case.expected_effects[: case.interruption_index]
    expected_suffix = case.expected_effects[case.interruption_index :]
    if case.applied_before_interruption != expected_prefix:
        violations.append("pre_interruption_effects_incorrect")
    if case.resumed_effects != expected_suffix:
        violations.append("resumed_effects_incorrect")
    if _first_duplicate((*case.applied_before_interruption, *case.resumed_effects)):
        violations.append("effect_replayed")
    if case.terminal_effects != case.expected_effects:
        violations.append("terminal_state_incorrect")
    return tuple(violations)


def _verify_unknown_outcome(steps: tuple[ExternalOutcomeAction, ...]) -> tuple[str, ...]:
    violations: list[str] = []
    phase = "ready"
    initial_invocation_seen = False
    for action in steps:
        if action == "invoke":
            if phase != "ready" or initial_invocation_seen:
                violations.append("duplicate_initial_invocation")
            initial_invocation_seen = True
            phase = "in_flight"
        elif action == "outcome_unknown":
            if phase != "in_flight":
                violations.append("unknown_outcome_without_call")
            else:
                phase = "unknown"
        elif action in {"observe_applied", "observe_absent"}:
            if phase != "unknown":
                violations.append("observation_without_unknown_outcome")
            phase = "applied" if action == "observe_applied" else "absent"
        elif action in {"confirmed_applied", "confirmed_absent"}:
            if phase != "in_flight":
                violations.append("confirmation_without_call")
            phase = "applied" if action == "confirmed_applied" else "absent"
        elif action == "retry":
            if phase == "unknown":
                violations.append("blind_retry_after_unknown")
                phase = "in_flight"
            elif phase == "applied":
                violations.append("retry_after_effect_applied")
                phase = "in_flight"
            elif phase == "absent":
                phase = "in_flight"
            else:
                violations.append("retry_without_confirmed_absence")
                phase = "in_flight"

    if not initial_invocation_seen:
        violations.append("initial_invocation_missing")
    if phase == "unknown":
        violations.append("unknown_outcome_not_observed")
    if phase != "applied":
        violations.append("operation_not_terminal")
    return tuple(violations)


def _verify_ownership_isolation(
    case: OwnershipIsolationCase, oracle: StateEquivalenceOracle
) -> tuple[str, ...]:
    unowned_before = tuple(
        state for state in case.state_before if state.owner_id != case.component_id
    )
    unowned_after = tuple(
        state for state in case.state_after if state.owner_id != case.component_id
    )
    if not unowned_before:
        return ("unowned_state_not_observed",)
    if _has_duplicate_state_keys(unowned_before) or _has_duplicate_state_keys(unowned_after):
        return ("duplicate_observable_state",)
    if not oracle.equivalent(unowned_before, unowned_after):
        return ("unowned_state_changed",)
    return ()


def _minimize_sequence[T](
    values: tuple[T, ...], preserves_failure: Callable[[tuple[T, ...]], bool]
) -> tuple[T, ...]:
    """Delta-debug a failing transition sequence while preserving its violation."""
    current = values
    granularity = 2
    while len(current) > 1:
        chunk_size = ceil(len(current) / granularity)
        reduced = False
        for start in range(0, len(current), chunk_size):
            candidate = current[:start] + current[start + chunk_size :]
            if candidate and preserves_failure(candidate):
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(current):
            break
        granularity = min(len(current), granularity * 2)
    return current


def _oracle_control_json() -> str:
    return json.dumps(
        {
            "kind": "oracle_negative_control",
            "left": [state.model_dump(mode="json") for state in _ORACLE_CONTROL_LEFT],
            "right": [state.model_dump(mode="json") for state in _ORACLE_CONTROL_RIGHT],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
