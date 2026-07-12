"""Docker-backed sandbox for isolated evidence execution."""

from __future__ import annotations

import asyncio
import os
import shutil
import tarfile
import tempfile
import time
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import docker
import structlog
from docker.errors import APIError, DockerException, NotFound

from evidence_first_harness.domain.exceptions import SandboxError
from evidence_first_harness.sandbox.commands import CommandValidator
from evidence_first_harness.sandbox.permissions import SandboxPermissions

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of a validated command executed inside a sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool


@dataclass(slots=True)
class _ContainerLease:
    """Bookkeeping for a live sandbox container."""

    created_monotonic: float
    deadline_monotonic: float
    read_only: bool


@dataclass(frozen=True, slots=True)
class _SyncExecResult:
    """Synchronous execution result before timeout handling."""

    exit_code: int
    stdout: str
    stderr: str
    output_limit_exceeded: bool


class DockerSandbox:
    """Manages ephemeral Docker containers for untrusted code execution."""

    def __init__(self, image: str = "evidence-first-harness-sandbox:latest") -> None:
        """Initialize the sandbox with a container image."""
        self._image = image
        self._permissions = SandboxPermissions()
        self._validator = CommandValidator(self._permissions)
        self._output_limit_bytes = 1_000_000
        self._client: docker.DockerClient | None = None
        self._leases: dict[str, _ContainerLease] = {}

    async def create(
        self,
        worktree_path: Path,
        network_mode: str = "disabled",
        cpu_limit: float = 2.0,
        memory_limit: str = "2g",
        read_only: bool = True,
        timeout_seconds: int = 300,
    ) -> str:
        """Create a sandbox container and return its container ID."""
        if cpu_limit <= 0:
            raise SandboxError("CPU limit must be positive")
        if timeout_seconds <= 0:
            raise SandboxError("Sandbox timeout must be positive")
        if not memory_limit.strip():
            raise SandboxError("Memory limit must be provided")

        resolved_worktree = self._permissions.validate_worktree_path(worktree_path)
        effective_network_mode = self._permissions.validate_network_mode(network_mode)

        logger.info(
            "sandbox_create_started",
            image=self._image,
            worktree_path=str(resolved_worktree),
            network_mode=effective_network_mode,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            read_only=read_only,
            timeout_seconds=timeout_seconds,
        )

        container_id = await asyncio.to_thread(
            self._create_sync,
            resolved_worktree,
            effective_network_mode,
            cpu_limit,
            memory_limit,
            read_only,
            timeout_seconds,
        )

        created_monotonic = time.monotonic()
        self._leases[container_id] = _ContainerLease(
            created_monotonic=created_monotonic,
            deadline_monotonic=created_monotonic + timeout_seconds,
            read_only=read_only,
        )

        logger.info("sandbox_created", container_id=container_id, image=self._image)
        return container_id

    async def exec_command(
        self,
        container_id: str,
        command: list[str],
        timeout_seconds: int = 120,
    ) -> CommandResult:
        """Execute a validated command inside the container."""
        lease = self._leases.get(container_id)
        if lease is None:
            raise SandboxError(f"Unknown sandbox container: {container_id}")

        validated_command = self._validator.validate(command, timeout_seconds)
        remaining_lifetime = max(0.0, lease.deadline_monotonic - time.monotonic())
        if remaining_lifetime <= 0:
            raise SandboxError(f"Sandbox lifetime has expired for container: {container_id}")

        effective_timeout = min(validated_command.timeout_seconds, int(remaining_lifetime))
        if effective_timeout <= 0:
            raise SandboxError(f"Sandbox lifetime has expired for container: {container_id}")

        logger.info(
            "sandbox_exec_started",
            container_id=container_id,
            command=validated_command.command,
            timeout_seconds=effective_timeout,
        )

        started_at = time.perf_counter()
        exec_task = asyncio.create_task(
            asyncio.to_thread(
                self._exec_sync,
                container_id,
                validated_command.command,
            )
        )

        try:
            sync_result = await asyncio.wait_for(exec_task, timeout=effective_timeout)
        except TimeoutError:
            await asyncio.to_thread(self._stop_sync, container_id)
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.warning(
                "sandbox_exec_timed_out",
                container_id=container_id,
                command=validated_command.command,
                timeout_seconds=effective_timeout,
                duration_ms=duration_ms,
            )
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {effective_timeout} seconds",
                duration_ms=duration_ms,
                timed_out=True,
            )

        duration_ms = (time.perf_counter() - started_at) * 1000
        stderr = sync_result.stderr
        if sync_result.output_limit_exceeded:
            stderr = self._append_status_message(
                stderr,
                f"Output limit exceeded at {self._output_limit_bytes} bytes",
            )

        result = CommandResult(
            exit_code=sync_result.exit_code,
            stdout=sync_result.stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=False,
        )

        logger.info(
            "sandbox_exec_completed",
            container_id=container_id,
            command=validated_command.command,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            output_limit_exceeded=sync_result.output_limit_exceeded,
        )
        return result

    async def copy_out(self, container_id: str, src: str, dest: Path) -> None:
        """Copy a file or directory from the sandbox to the host."""
        if container_id not in self._leases:
            raise SandboxError(f"Unknown sandbox container: {container_id}")

        source_path = self._permissions.validate_container_path(src)
        logger.info(
            "sandbox_copy_out_started",
            container_id=container_id,
            src=str(source_path),
            dest=str(dest),
        )

        await asyncio.to_thread(self._copy_out_sync, container_id, str(source_path), dest)

        logger.info(
            "sandbox_copy_out_completed",
            container_id=container_id,
            src=str(source_path),
            dest=str(dest),
        )

    async def destroy(self, container_id: str) -> None:
        """Stop and remove the sandbox container."""
        logger.info("sandbox_destroy_started", container_id=container_id)
        self._leases.pop(container_id, None)
        await asyncio.to_thread(self._destroy_sync, container_id)
        logger.info("sandbox_destroy_completed", container_id=container_id)

    def _create_sync(
        self,
        worktree_path: Path,
        network_mode: str,
        cpu_limit: float,
        memory_limit: str,
        read_only: bool,
        timeout_seconds: int,
    ) -> str:
        """Synchronously create the container via the Docker SDK."""
        client = self._get_client()
        try:
            container = client.containers.run(
                self._image,
                command=["sleep", str(timeout_seconds)],
                detach=True,
                auto_remove=False,
                user="sandbox",
                working_dir=self._permissions.workspace_path,
                network_mode=self._permissions.docker_network_mode(network_mode),
                nano_cpus=int(cpu_limit * 1_000_000_000),
                mem_limit=memory_limit,
                read_only=self._permissions.read_only_root_filesystem,
                volumes=self._permissions.build_mounts(worktree_path, read_only=read_only),
                tmpfs=self._permissions.build_tmpfs(),
                environment=self._permissions.build_environment(
                    os.environ,
                    network_mode=network_mode,
                ),
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=256,
                init=True,
                tty=False,
                stdin_open=False,
                labels={"efh.managed": "true"},
            )
            container_id = container.id
            if container_id is None:
                raise SandboxError("Docker did not return a container ID")
            return container_id
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to create sandbox container", exc) from exc

    def _exec_sync(self, container_id: str, command: list[str]) -> _SyncExecResult:
        """Synchronously execute a command and collect bounded output."""
        client = self._get_client()
        try:
            container = client.containers.get(container_id)
            container.reload()
            if container.status != "running":
                raise SandboxError(
                    f"Sandbox container is not running: {container_id} ({container.status})"
                )

            api_client: Any = client.api
            exec_create_result = cast(
                "dict[str, Any]",
                api_client.exec_create(
                    container_id,
                    command,
                    stdout=True,
                    stderr=True,
                    stdin=False,
                    tty=False,
                    user="sandbox",
                    workdir=self._permissions.workspace_path,
                ),
            )
            exec_id = cast("str", exec_create_result["Id"])

            stream = api_client.exec_start(exec_id, stream=True, demux=True)
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            total_bytes = 0
            output_limit_exceeded = False

            for chunk in stream:
                stdout_chunk, stderr_chunk = self._normalize_stream_chunk(chunk)
                for current_chunk, bucket in (
                    (stdout_chunk, stdout_chunks),
                    (stderr_chunk, stderr_chunks),
                ):
                    if not current_chunk:
                        continue

                    if total_bytes >= self._output_limit_bytes:
                        output_limit_exceeded = True
                        break

                    remaining_bytes = self._output_limit_bytes - total_bytes
                    bucket.append(current_chunk[:remaining_bytes])
                    total_bytes += min(len(current_chunk), remaining_bytes)

                    if (
                        len(current_chunk) > remaining_bytes
                        or total_bytes >= self._output_limit_bytes
                    ):
                        output_limit_exceeded = True
                        break

                if output_limit_exceeded:
                    self._stop_sync(container_id)
                    break

            try:
                exec_details = cast("dict[str, Any]", api_client.exec_inspect(exec_id))
                exit_code = int(exec_details.get("ExitCode") or 0)
            except APIError:
                exit_code = -1

            if output_limit_exceeded:
                exit_code = -1

            return _SyncExecResult(
                exit_code=exit_code,
                stdout=b"".join(stdout_chunks).decode("utf-8", errors="replace"),
                stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace"),
                output_limit_exceeded=output_limit_exceeded,
            )
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to execute command in sandbox", exc) from exc

    def _copy_out_sync(self, container_id: str, src: str, dest: Path) -> None:
        """Synchronously copy files out of a container via a tar stream."""
        if dest.exists():
            raise SandboxError(f"Destination already exists: {dest}")

        client = self._get_client()
        try:
            api_client: Any = client.api
            archive_stream, _ = cast(
                "tuple[Iterable[bytes], Any]",
                api_client.get_archive(container_id, src),
            )
            with tempfile.TemporaryDirectory(prefix="efh-copy-out-") as tmp_dir:
                archive_path = Path(tmp_dir) / "archive.tar"
                with archive_path.open("wb") as archive_file:
                    for chunk in archive_stream:
                        archive_file.write(chunk)

                extract_root = Path(tmp_dir) / "extract"
                extract_root.mkdir()

                with tarfile.open(archive_path, mode="r:*") as archive:
                    self._safe_extract_archive(archive, extract_root)

                extracted_children = list(extract_root.iterdir())
                if len(extracted_children) != 1:
                    raise SandboxError("Unexpected archive layout returned by Docker")

                extracted_path = extracted_children[0]
                dest.parent.mkdir(parents=True, exist_ok=True)
                if extracted_path.is_dir():
                    shutil.copytree(extracted_path, dest)
                else:
                    shutil.copy2(extracted_path, dest)
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to copy files out of sandbox", exc) from exc
        except (tarfile.TarError, OSError) as exc:
            raise SandboxError(f"Failed to extract sandbox archive: {exc}") from exc

    def _destroy_sync(self, container_id: str) -> None:
        """Synchronously stop and remove a sandbox container."""
        client = self._get_client()
        try:
            container = client.containers.get(container_id)
        except NotFound:
            return
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to locate sandbox container", exc) from exc

        try:
            with suppress(APIError):
                container.stop(timeout=1)
            container.remove(force=True)
        except NotFound:
            return
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to destroy sandbox container", exc) from exc

    def _stop_sync(self, container_id: str) -> None:
        """Synchronously stop a running container."""
        client = self._get_client()
        try:
            container = client.containers.get(container_id)
            container.stop(timeout=1)
        except NotFound:
            return
        except APIError:
            return
        except DockerException as exc:
            raise self._wrap_docker_error("Failed to stop sandbox container", exc) from exc

    def _get_client(self) -> docker.DockerClient:
        """Return a lazily initialized Docker client."""
        if self._client is None:
            try:
                client = docker.from_env()
                cast("Any", client).ping()
            except DockerException as exc:
                raise SandboxError("Docker daemon is unavailable") from exc
            self._client = client
        return self._client

    def _safe_extract_archive(self, archive: tarfile.TarFile, destination: Path) -> None:
        """Extract a tar archive while blocking path traversal and links."""
        destination_resolved = destination.resolve()
        members = archive.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise SandboxError("Sandbox archive cannot contain symbolic links")
            if not member.isdir() and not member.isfile():
                raise SandboxError("Sandbox archive contains an unsupported file type")

            member_destination = (destination / member.name).resolve()
            if (
                destination_resolved not in member_destination.parents
                and member_destination != destination_resolved
            ):
                raise SandboxError("Sandbox archive attempted path traversal")

        for member in members:
            target_path = destination / member.name
            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_file = archive.extractfile(member)
            if extracted_file is None:
                raise SandboxError("Sandbox archive file payload could not be read")
            with extracted_file, target_path.open("wb") as target_file:
                shutil.copyfileobj(extracted_file, target_file)

    def _wrap_docker_error(self, message: str, error: DockerException) -> SandboxError:
        """Convert Docker SDK errors into sandbox domain errors."""
        if "connection aborted" in str(error).lower():
            return SandboxError("Docker daemon is unavailable")
        return SandboxError(f"{message}: {error}")

    @staticmethod
    def _append_status_message(message: str, status: str) -> str:
        """Append a status line to a stderr message."""
        if not message:
            return status
        return f"{message}\n{status}"

    @staticmethod
    def _normalize_stream_chunk(
        chunk: tuple[bytes | None, bytes | None] | bytes | None,
    ) -> tuple[bytes | None, bytes | None]:
        """Normalize Docker stream chunks into stdout and stderr byte strings."""
        if chunk is None:
            return None, None
        if isinstance(chunk, tuple):
            return chunk
        return chunk, None
