"""Sandbox permission definitions and enforcement."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from evidence_first_harness.domain.exceptions import SandboxError

NetworkMode = Literal["disabled", "proxy", "full"]

_FORBIDDEN_ENVIRONMENT_PATTERN = re.compile(
    r"(SECRET|TOKEN|PASSWORD|CREDENTIAL|AWS_|AZURE_|GCP_|GOOGLE_APPLICATION_CREDENTIALS|"
    r"DOCKER_|KUBECONFIG|SSH_AUTH_SOCK|SESSION)",
    re.IGNORECASE,
)


class SandboxPermissions(BaseModel):
    """Defines the deterministic security boundary for a sandbox container."""

    model_config = {"extra": "forbid", "frozen": True}

    workspace_path: str = "/workspace"
    temp_path: str = "/tmp/efh"
    network_mode: NetworkMode = "disabled"
    read_only_root_filesystem: bool = True
    writable_tmpfs_options: str = "rw,nosuid,nodev,noexec,size=268435456"
    allowed_environment_variables: tuple[str, ...] = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_TRUSTED_HOST",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
    )
    allowed_network_hosts: tuple[str, ...] = Field(default_factory=tuple)
    internal_environment: dict[str, str] = Field(
        default_factory=lambda: {
            "HOME": "/tmp/efh/home",
            "TMPDIR": "/tmp/efh/tmp",
            "XDG_CACHE_HOME": "/tmp/efh/cache",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": "/tmp/efh/pycache",
            "PIP_CACHE_DIR": "/tmp/efh/pip-cache",
            "RUFF_CACHE_DIR": "/tmp/efh/ruff-cache",
            "PYTEST_ADDOPTS": "--cache-dir=/tmp/efh/pytest-cache",
        }
    )

    def validate_worktree_path(self, worktree_path: Path) -> Path:
        """Validate that the host worktree path is safe to mount."""
        try:
            resolved_path = worktree_path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise SandboxError(f"Worktree path does not exist: {worktree_path}") from exc

        if not resolved_path.is_dir():
            raise SandboxError(f"Worktree path must be a directory: {resolved_path}")
        if resolved_path == Path("/var/run/docker.sock"):
            raise SandboxError("Host Docker socket access is forbidden")

        return resolved_path

    def validate_network_mode(self, network_mode: str | None = None) -> NetworkMode:
        """Validate the configured network mode."""
        effective_mode = network_mode or self.network_mode
        if effective_mode not in {"disabled", "proxy", "full"}:
            raise SandboxError(f"Unsupported network mode: {effective_mode}")
        return effective_mode

    def docker_network_mode(self, network_mode: str | None = None) -> str:
        """Translate the logical network mode to a Docker network mode."""
        effective_mode = self.validate_network_mode(network_mode)
        if effective_mode == "disabled":
            return "none"
        return "bridge"

    def build_mounts(self, worktree_path: Path, *, read_only: bool) -> dict[str, dict[str, str]]:
        """Build the bind mounts for the sandbox container."""
        resolved_path = self.validate_worktree_path(worktree_path)
        return {
            str(resolved_path): {
                "bind": self.workspace_path,
                "mode": "ro" if read_only else "rw",
            }
        }

    def build_tmpfs(self) -> dict[str, str]:
        """Build writable tmpfs mounts for temporary sandbox data."""
        return {self.temp_path: self.writable_tmpfs_options}

    def build_environment(
        self,
        source_environment: Mapping[str, str] | None = None,
        *,
        network_mode: str | None = None,
    ) -> dict[str, str]:
        """Build the container environment from safe internal and host variables."""
        effective_mode = self.validate_network_mode(network_mode)
        host_environment = source_environment or os.environ
        environment = dict(self.internal_environment)

        for key in self.allowed_environment_variables:
            value = host_environment.get(key)
            if value is None:
                continue
            if effective_mode == "disabled":
                continue
            self._validate_environment_variable(key, value)
            environment[key] = value

        if effective_mode == "proxy" and not self._has_proxy_configuration(environment):
            raise SandboxError(
                "Proxy network mode requires approved proxy or package index configuration"
            )

        self._ensure_no_production_credentials(environment)
        return environment

    def validate_container_path(
        self,
        container_path: str,
        *,
        allow_temp: bool = True,
    ) -> PurePosixPath:
        """Validate a path inside the container and prevent traversal."""
        candidate = container_path.strip()
        if not candidate:
            raise SandboxError("Container path cannot be empty")
        if "\x00" in candidate:
            raise SandboxError("Container path cannot contain null bytes")

        raw_path = PurePosixPath(candidate.split("::", 1)[0])
        if raw_path.is_absolute():
            normalized_path = raw_path
        else:
            normalized_path = PurePosixPath(self.workspace_path) / raw_path

        if ".." in normalized_path.parts:
            raise SandboxError(f"Path traversal is not allowed: {container_path}")

        if self._is_under_root(normalized_path, self.workspace_path):
            return normalized_path
        if allow_temp and self._is_under_root(normalized_path, self.temp_path):
            return normalized_path

        raise SandboxError(f"Path is outside sandbox roots: {container_path}")

    def _validate_environment_variable(self, key: str, value: str) -> None:
        """Validate an allowlisted environment variable value."""
        if _FORBIDDEN_ENVIRONMENT_PATTERN.search(key):
            raise SandboxError(f"Forbidden environment variable: {key}")

        if key in {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "PIP_INDEX_URL",
            "PIP_EXTRA_INDEX_URL",
            "UV_INDEX_URL",
            "UV_EXTRA_INDEX_URL",
        }:
            self._validate_network_url(key, value)
            return

        if key in {"NO_PROXY", "PIP_TRUSTED_HOST"}:
            self._validate_host_list(key, value)

    def _validate_network_url(self, key: str, value: str) -> None:
        """Validate a network URL against the approved host allowlist."""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise SandboxError(f"Unsupported URL scheme for {key}")
        if parsed.username or parsed.password:
            raise SandboxError(f"Credentials are not allowed in {key}")

        host = parsed.hostname
        if host is None:
            raise SandboxError(f"Missing hostname in {key}")
        if self.allowed_network_hosts and host not in self.allowed_network_hosts:
            raise SandboxError(f"Network host is not allowlisted for {key}: {host}")

    def _validate_host_list(self, key: str, value: str) -> None:
        """Validate a comma-separated host allowlist value."""
        if not value.strip():
            raise SandboxError(f"{key} cannot be empty")

        if not self.allowed_network_hosts:
            raise SandboxError(f"{key} requires configured allowlisted network hosts")

        for host in (item.strip() for item in value.split(",")):
            if not host:
                continue
            if host not in self.allowed_network_hosts:
                raise SandboxError(f"Network host is not allowlisted for {key}: {host}")

    def _has_proxy_configuration(self, environment: Mapping[str, str]) -> bool:
        """Return whether the environment contains approved proxy configuration."""
        return any(
            key in environment
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "PIP_INDEX_URL",
                "PIP_EXTRA_INDEX_URL",
                "UV_INDEX_URL",
                "UV_EXTRA_INDEX_URL",
            )
        )

    def _ensure_no_production_credentials(self, environment: Mapping[str, str]) -> None:
        """Ensure no credential-like variables are passed into the sandbox."""
        for key in environment:
            if _FORBIDDEN_ENVIRONMENT_PATTERN.search(key):
                raise SandboxError(f"Credential-like environment variable is forbidden: {key}")

    @staticmethod
    def _is_under_root(path: PurePosixPath, root: str) -> bool:
        """Return whether a path is within a configured sandbox root."""
        root_path = PurePosixPath(root)
        return path == root_path or root_path in path.parents
