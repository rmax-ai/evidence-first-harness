"""Validated command definitions for sandbox execution."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from evidence_first_harness.domain.exceptions import SandboxError
from evidence_first_harness.sandbox.permissions import SandboxPermissions

_SHELL_METACHARACTER_PATTERN = re.compile(r"[;&|><`$!\n\r\0]")

ValueType = Literal["int", "path", "text"]


@dataclass(frozen=True, slots=True)
class ValidatedCommand:
    """A command that passed deterministic validation."""

    command: list[str]
    timeout_seconds: int


class CommandRule(BaseModel):
    """Validation rule for an approved command."""

    model_config = {"extra": "forbid", "frozen": True}

    executable: str
    timeout_seconds: int = 120
    max_arguments: int = 32
    subcommands: tuple[str, ...] = Field(default_factory=tuple)
    boolean_options: tuple[str, ...] = Field(default_factory=tuple)
    value_options: dict[str, ValueType] = Field(default_factory=dict)
    allow_path_arguments: bool = True


class CommandValidator:
    """Validates sandbox commands against a deterministic allowlist."""

    def __init__(
        self,
        permissions: SandboxPermissions | None = None,
        rules: Sequence[CommandRule] | None = None,
    ) -> None:
        """Initialize the validator with sandbox permissions and rules."""
        self._permissions = permissions or SandboxPermissions()
        command_rules = tuple(rules or _default_rules())
        self._rules = {rule.executable: rule for rule in command_rules}

    def validate(
        self,
        command: Sequence[str],
        timeout_seconds: int | None = None,
    ) -> ValidatedCommand:
        """Validate a command and return a normalized execution request."""
        if not command:
            raise SandboxError("Command cannot be empty")

        executable = PurePosixPath(command[0]).name
        if executable != command[0]:
            raise SandboxError("Executable paths are not allowed")

        rule = self._rules.get(executable)
        if rule is None:
            raise SandboxError(f"Command is not allowlisted: {command[0]}")

        normalized_command = [executable, *self._validate_arguments(rule, list(command[1:]))]
        effective_timeout = timeout_seconds if timeout_seconds is not None else rule.timeout_seconds

        if effective_timeout <= 0:
            raise SandboxError("Timeout must be positive")
        if effective_timeout > rule.timeout_seconds:
            raise SandboxError(
                "Timeout exceeds limit for "
                f"{executable}: {effective_timeout} > {rule.timeout_seconds}"
            )

        return ValidatedCommand(command=normalized_command, timeout_seconds=effective_timeout)

    def _validate_arguments(self, rule: CommandRule, arguments: list[str]) -> list[str]:
        """Validate argument structure for a specific rule."""
        if len(arguments) > rule.max_arguments:
            raise SandboxError(
                f"Too many arguments for {rule.executable}: {len(arguments)} > {rule.max_arguments}"
            )

        if rule.executable in {"python", "python3"}:
            return self._validate_python_arguments(arguments)
        if rule.executable == "git":
            return self._validate_git_arguments(rule, arguments)

        validated_arguments: list[str] = []
        current_index = 0

        if rule.subcommands:
            if not arguments:
                raise SandboxError(f"{rule.executable} requires a subcommand")
            subcommand = arguments[0]
            self._validate_plain_token(subcommand)
            if subcommand not in rule.subcommands:
                raise SandboxError(
                    f"Subcommand is not allowlisted for {rule.executable}: {subcommand}"
                )
            validated_arguments.append(subcommand)
            current_index = 1

        while current_index < len(arguments):
            argument = arguments[current_index]
            self._validate_argument_token(argument)

            if argument.startswith("-"):
                validated_arguments.extend(self._validate_option(rule, arguments, current_index))
                current_index += 2 if self._option_consumes_value(rule, argument) else 1
                continue

            if not rule.allow_path_arguments:
                raise SandboxError(
                    f"Positional arguments are not allowed for {rule.executable}: {argument}"
                )

            self._permissions.validate_container_path(argument)
            validated_arguments.append(argument)
            current_index += 1

        return validated_arguments

    def _validate_python_arguments(self, arguments: list[str]) -> list[str]:
        """Validate Python interpreter execution with a script path only."""
        if not arguments:
            raise SandboxError("Python execution requires a script path")

        validated_arguments: list[str] = []
        current_index = 0
        while current_index < len(arguments) and arguments[current_index] in {"-B", "-I", "-u"}:
            validated_arguments.append(arguments[current_index])
            current_index += 1

        if current_index >= len(arguments):
            raise SandboxError("Python execution requires a script path")

        script_path = arguments[current_index]
        self._validate_argument_token(script_path)
        self._permissions.validate_container_path(script_path)
        validated_arguments.append(script_path)
        current_index += 1

        while current_index < len(arguments):
            argument = arguments[current_index]
            self._validate_argument_token(argument)
            if self._looks_like_path(argument):
                self._permissions.validate_container_path(argument)
            validated_arguments.append(argument)
            current_index += 1

        return validated_arguments

    def _validate_git_arguments(self, rule: CommandRule, arguments: list[str]) -> list[str]:
        """Validate the limited Git subcommands allowed in the sandbox."""
        if not arguments:
            raise SandboxError("git requires a subcommand")

        subcommand = arguments[0]
        self._validate_plain_token(subcommand)
        if subcommand not in rule.subcommands:
            raise SandboxError(f"Subcommand is not allowlisted for git: {subcommand}")

        validated_arguments = [subcommand]
        current_index = 1
        while current_index < len(arguments):
            argument = arguments[current_index]
            self._validate_argument_token(argument)

            if argument == "--":
                validated_arguments.append(argument)
                current_index += 1
                continue

            if argument.startswith("-"):
                validated_arguments.extend(self._validate_option(rule, arguments, current_index))
                current_index += 2 if self._option_consumes_value(rule, argument) else 1
                continue

            self._permissions.validate_container_path(argument)
            validated_arguments.append(argument)
            current_index += 1

        return validated_arguments

    def _validate_option(
        self,
        rule: CommandRule,
        arguments: list[str],
        index: int,
    ) -> list[str]:
        """Validate one option token and any attached value."""
        option = arguments[index]
        normalized_option, inline_value = self._split_option(option)

        if normalized_option in rule.boolean_options:
            if inline_value is not None:
                raise SandboxError(f"Boolean option cannot take a value: {normalized_option}")
            return [option]

        value_type = rule.value_options.get(normalized_option)
        if value_type is None:
            raise SandboxError(
                f"Option is not allowlisted for {rule.executable}: {normalized_option}"
            )

        if inline_value is None:
            if index + 1 >= len(arguments):
                raise SandboxError(f"Option requires a value: {normalized_option}")
            value = arguments[index + 1]
            self._validate_argument_token(value)
            self._validate_option_value(value_type, value)
            return [option, value]

        self._validate_plain_token(inline_value)
        self._validate_option_value(value_type, inline_value)
        return [option]

    def _validate_option_value(self, value_type: ValueType, value: str) -> None:
        """Validate a typed option value."""
        if value_type == "int":
            if not value.isdigit():
                raise SandboxError(f"Expected integer option value, got: {value}")
            return

        if value_type == "path":
            self._permissions.validate_container_path(value)
            return

        self._validate_plain_token(value)

    def _option_consumes_value(self, rule: CommandRule, option: str) -> bool:
        """Return whether an option consumes the following argument."""
        normalized_option, inline_value = self._split_option(option)
        return normalized_option in rule.value_options and inline_value is None

    def _validate_argument_token(self, token: str) -> None:
        """Validate an argument token and reject shell vectors."""
        if not token:
            raise SandboxError("Command arguments cannot be empty")
        if _SHELL_METACHARACTER_PATTERN.search(token):
            raise SandboxError(f"Shell metacharacters are not allowed: {token}")

    def _validate_plain_token(self, token: str) -> None:
        """Validate a plain token that is not treated as a path."""
        self._validate_argument_token(token)
        if token.startswith(".."):
            raise SandboxError(f"Path traversal is not allowed: {token}")

    def _looks_like_path(self, token: str) -> bool:
        """Return whether a token should be treated as a container path."""
        if token in {".", ".."}:
            return True
        path_portion = token.split("::", 1)[0]
        if path_portion.startswith(("/", ".")):
            return True
        if "/" in path_portion:
            return True
        return path_portion.endswith(
            (".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".txt")
        )

    @staticmethod
    def _split_option(option: str) -> tuple[str, str | None]:
        """Split an option token into its flag and optional inline value."""
        if "=" not in option:
            return option, None
        normalized_option, inline_value = option.split("=", 1)
        return normalized_option, inline_value


def _default_rules() -> tuple[CommandRule, ...]:
    """Return the default deterministic command allowlist."""
    return (
        CommandRule(
            executable="ruff",
            timeout_seconds=120,
            subcommands=("check", "format"),
            boolean_options=(
                "--check",
                "--diff",
                "--fix",
                "--force-exclude",
                "--isolated",
                "--preview",
                "--quiet",
                "--show-files",
                "--show-fixes",
                "--statistics",
                "--unsafe-fixes",
                "-q",
            ),
            value_options={
                "--config": "path",
                "--exclude": "text",
                "--extend-exclude": "text",
                "--ignore": "text",
                "--line-length": "int",
                "--output-format": "text",
                "--select": "text",
                "--target-version": "text",
            },
        ),
        CommandRule(
            executable="pyright",
            timeout_seconds=180,
            boolean_options=("--outputjson", "--skipunannotated", "--stats", "--verbose"),
            value_options={
                "--level": "text",
                "--project": "path",
                "--pythonplatform": "text",
                "--pythonversion": "text",
                "--threads": "int",
                "--venvpath": "path",
            },
        ),
        CommandRule(
            executable="pytest",
            timeout_seconds=300,
            boolean_options=(
                "--collect-only",
                "--disable-warnings",
                "--ff",
                "--last-failed",
                "--lf",
                "-q",
                "-v",
                "-x",
            ),
            value_options={
                "--cov": "path",
                "--cov-report": "text",
                "--maxfail": "int",
                "--rootdir": "path",
                "--tb": "text",
                "-k": "text",
                "-m": "text",
            },
        ),
        CommandRule(
            executable="git",
            timeout_seconds=120,
            subcommands=("diff", "status"),
            boolean_options=(
                "--branch",
                "--cached",
                "--name-only",
                "--name-status",
                "--no-ext-diff",
                "--porcelain",
                "--short",
                "--stat",
                "-s",
            ),
            value_options={"--unified": "int"},
        ),
        CommandRule(
            executable="python",
            timeout_seconds=300,
            boolean_options=("-B", "-I", "-u"),
            allow_path_arguments=True,
        ),
        CommandRule(
            executable="python3",
            timeout_seconds=300,
            boolean_options=("-B", "-I", "-u"),
            allow_path_arguments=True,
        ),
    )
