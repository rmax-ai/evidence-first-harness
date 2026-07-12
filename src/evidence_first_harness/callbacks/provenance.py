"""Provenance recorder — append-only hash-chained event stream.

Section 19 of the spec. Every significant action in the harness is recorded
as a ProvenanceEvent with cryptographic chaining for tamper detection.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from evidence_first_harness.domain.provenance import ProvenanceEvent

logger = structlog.get_logger()


class ProvenanceRecorder:
    """Records an append-only, hash-chained event stream.

    Each event links to the previous event's digest, making tampering
    detectable by verifying the chain from any point.
    """

    def __init__(self, run_id: str, store_path: Path | str) -> None:
        self._run_id = run_id
        self._store_path = Path(store_path)
        self._store_path.mkdir(parents=True, exist_ok=True)
        self._events_path = self._store_path / f"{run_id}_provenance.jsonl"
        self._previous_digest = self._digest({"genesis": run_id})  # Genesis chain root

    def record(
        self,
        actor_type: str,
        actor_id: str,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        model: str | None = None,
        tool: str | None = None,
        authorization: str | None = None,
    ) -> ProvenanceEvent:
        """Record a new provenance event and return it.

        Args:
            actor_type: "agent", "tool", "human", "system"
            actor_id: Identifier of the actor
            action: What was done
            input_data: Input to the action (serializable)
            output_data: Output from the action (serializable)
            model: Model used (for agent actions)
            tool: Tool used (for tool actions)
            authorization: Authorization that allowed this action

        Returns:
            The recorded ProvenanceEvent.
        """
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(UTC)

        input_digest = self._digest(input_data)
        output_digest = self._digest(output_data)

        event = ProvenanceEvent(
            event_id=event_id,
            run_id=self._run_id,
            timestamp=timestamp,
            actor_type=actor_type,
            actor_id=actor_id,
            model=model,
            action=action,
            input_digest=input_digest,
            output_digest=output_digest,
            tool=tool,
            authorization=authorization,
            previous_event_digest=self._previous_digest,
        )

        # Write to the append-only log
        with open(self._events_path, "a") as f:
            f.write(event.model_dump_json() + "\n")

        # Update chain — use JSON-mode dump so digest matches serialized form
        self._previous_digest = self._digest(json.loads(event.model_dump_json()))

        return event

    def verify_chain(self) -> dict[str, Any]:
        """Verify the integrity of the entire event chain.

        Returns:
            Dict with verification results and any detected tampering.
        """
        if not self._events_path.exists():
            return {"valid": True, "event_count": 0, "tampered": []}

        events: list[dict[str, Any]] = []
        for line in self._events_path.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))

        tampered: list[str] = []
        previous_digest = self._digest({"genesis": self._run_id})  # Genesis root

        for i, event_data in enumerate(events):
            expected_prev = event_data.get("previous_event_digest", "")
            if i == 0:
                # First event: don't verify previous — it chains from genesis
                pass
            elif expected_prev != previous_digest:
                tampered.append(
                    f"Event {i} ({event_data.get('event_id', 'unknown')}): "
                    f"expected previous={previous_digest[:16]}..., "
                    f"got {expected_prev[:16]}..."
                )
            previous_digest = self._digest(event_data)

        return {
            "valid": len(tampered) == 0,
            "event_count": len(events),
            "tampered": tampered,
        }

    @staticmethod
    def _digest(data: Any) -> str:
        """Compute SHA-256 digest of serializable data."""
        if data is None:
            return "sha256:" + hashlib.sha256(b"").hexdigest()
        serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return "sha256:" + hashlib.sha256(serialized).hexdigest()
