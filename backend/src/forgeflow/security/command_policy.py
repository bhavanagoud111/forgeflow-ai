"""Execution policy for commands run inside workspaces.

Commands are never passed through a shell. A command is an argv list that must match
one of the allowlisted shapes below; anything else is rejected before a sandbox is
touched. Models cannot propose commands directly: agents choose from verification
profiles detected from the repository, and those profiles are validated here too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAFE_ARG = re.compile(r"^[A-Za-z0-9_./:=@,+-]*$")


class CommandRejected(ValueError):
    pass


@dataclass(frozen=True)
class CommandRule:
    name: str
    prefix: tuple[str, ...]
    allow_extra_args: bool = True
    needs_network: bool = False


RULES: tuple[CommandRule, ...] = (
    CommandRule("pytest", ("python", "-m", "pytest")),
    CommandRule("ruff-check", ("python", "-m", "ruff", "check")),
    CommandRule("ruff-format-check", ("python", "-m", "ruff", "format", "--check")),
    CommandRule("mypy", ("python", "-m", "mypy")),
    CommandRule("compileall", ("python", "-m", "compileall", "-q")),
    CommandRule("npm-test", ("npm", "test", "--", "--watch=false"), allow_extra_args=False),
    CommandRule("npm-lint", ("npm", "run", "lint"), allow_extra_args=False),
    CommandRule("npm-typecheck", ("npm", "run", "typecheck"), allow_extra_args=False),
    CommandRule("npm-build", ("npm", "run", "build"), allow_extra_args=False),
    CommandRule("go-test", ("go", "test", "./...")),
    CommandRule("go-vet", ("go", "vet", "./...")),
    CommandRule(
        "pip-install",
        ("python", "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "-r"),
        needs_network=True,
    ),
)


def validate_command(argv: list[str], *, allow_dependency_install: bool = False) -> CommandRule:
    """Return the matching rule or raise ``CommandRejected``."""
    if not argv:
        raise CommandRejected("empty command")
    for arg in argv:
        if not _SAFE_ARG.match(arg):
            raise CommandRejected(f"argument contains disallowed characters: {arg!r}")
        if arg.startswith("/") or ".." in arg.split("/"):
            raise CommandRejected(f"argument escapes the workspace: {arg!r}")
    for rule in RULES:
        n = len(rule.prefix)
        if tuple(argv[:n]) != rule.prefix:
            continue
        if not rule.allow_extra_args and len(argv) != n:
            raise CommandRejected(f"{rule.name} does not accept extra arguments")
        if rule.needs_network and not allow_dependency_install:
            raise CommandRejected("dependency installation is disabled by policy")
        if rule.name == "pip-install" and (len(argv) != n + 1 or not argv[-1].endswith(".txt")):
            raise CommandRejected("pip install only accepts a single requirements file")
        return rule
    raise CommandRejected(f"command is not on the allowlist: {' '.join(argv[:4])}")
