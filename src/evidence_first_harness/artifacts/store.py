"""Artifact store with cryptographic integrity.

Section 10.6 and section 15 of the spec. Stores artifacts immutably,
computes digests, and verifies integrity on retrieval.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from evidence_first_harness.domain.exceptions import ArtifactError

logger = structlog.get_logger()


class ArtifactStore:
    """Immutable artifact storage with SHA-256 integrity verification.

    Artifacts are stored as files on disk with a companion index.
    Every write computes a digest; every read verifies it.
    """

    def __init__(self, root_path: Path | str) -> None:
        self._root = Path(root_path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / "index.jsonl"
        self._artifacts_dir = self._root / "objects"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        kind: str,
        content: bytes | str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference:
        """Store an artifact and return its reference.

        Args:
            kind: Artifact kind (e.g., "specification", "evidence_record", "patch").
            content: The artifact content (bytes or string).
            metadata: Optional metadata dict stored alongside.

        Returns:
            An ArtifactReference with ID, digest, and path.
        """
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        digest = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = f"art_{digest[:16]}"

        # Write the artifact blob
        blob_path = self._artifacts_dir / artifact_id
        blob_path.write_bytes(content_bytes)

        # Build the index entry
        now = datetime.now(UTC)
        entry: dict[str, Any] = {
            "artifact_id": artifact_id,
            "kind": kind,
            "digest": f"sha256:{digest}",
            "size_bytes": len(content_bytes),
            "stored_at": now.isoformat(),
            "metadata": metadata or {},
        }

        # Append to index
        with open(self._index_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        logger.info(
            "artifact_stored",
            artifact_id=artifact_id,
            kind=kind,
            size_bytes=len(content_bytes),
            digest=f"sha256:{digest[:16]}...",
        )

        return ArtifactReference(
            artifact_id=artifact_id,
            kind=kind,
            digest=f"sha256:{digest}",
            path=blob_path,
            size_bytes=len(content_bytes),
        )

    def retrieve(self, artifact_id: str) -> bytes:
        """Retrieve an artifact by ID, verifying integrity.

        Args:
            artifact_id: The artifact ID to retrieve.

        Returns:
            The artifact content as bytes.

        Raises:
            ArtifactError: If the artifact is not found or integrity check fails.
        """
        blob_path = self._artifacts_dir / artifact_id
        if not blob_path.exists():
            raise ArtifactError(f"Artifact not found: {artifact_id}")

        content = blob_path.read_bytes()
        expected_digest = self._get_digest(artifact_id)

        if expected_digest:
            actual_digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if actual_digest != expected_digest:
                raise ArtifactError(
                    f"Integrity check failed for {artifact_id}: "
                    f"expected {expected_digest}, got {actual_digest}"
                )

        return content

    def _get_digest(self, artifact_id: str) -> str | None:
        """Look up the digest for an artifact from the index."""
        if not self._index_path.exists():
            return None

        for line in self._index_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("artifact_id") == artifact_id:
                return entry.get("digest", "")

        return None


class ArtifactReference:
    """A reference to a stored artifact."""

    def __init__(
        self,
        artifact_id: str,
        kind: str,
        digest: str,
        path: Path,
        size_bytes: int,
    ) -> None:
        self.artifact_id = artifact_id
        self.kind = kind
        self.digest = digest
        self.path = path
        self.size_bytes = size_bytes

    def __repr__(self) -> str:
        return f"ArtifactReference({self.artifact_id}, {self.kind}, {self.digest[:24]})"
