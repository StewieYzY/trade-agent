"""Shared G1 production-path isolation boundary."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class ProductionPathViolation(ValueError):
    """A caller-provided path can resolve to or contain a G1 production root."""


_PRODUCTION_ROOT_RELATIVE_PATHS = (
    ("data", "cache"),
    ("watchlist",),
    ("debate",),
    ("ranking",),
    ("rankings",),
    ("data", "canonical_snapshot"),
    ("data", "canonical_snapshots"),
    ("data", "canonical-snapshot"),
    ("data", "canonical-snapshots"),
    ("canonical_snapshot",),
    ("canonical_snapshots",),
    ("canonical-snapshot",),
    ("canonical-snapshots",),
    ("data", "growth_diagnostic"),
    ("data", "growth_diagnostics"),
    ("data", "growth-diagnostic"),
    ("data", "growth-diagnostics"),
    ("growth_diagnostic",),
    ("growth_diagnostics",),
    ("growth-diagnostic",),
    ("growth-diagnostics",),
    ("diagnostic",),
    ("diagnostics",),
)


def _default_repo_root() -> Path:
    return _resolve_path(Path(__file__)).parents[3]


def _resolve_path(path: str | Path, *, seen_symlinks: frozenset[str] = frozenset()) -> Path:
    absolute = _absolute_without_resolving(Path(path))
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts):
        if part in {"", "."}:
            continue
        if part == "..":
            current = current.parent
            continue
        candidate = current / part
        if candidate.is_symlink():
            key = os.path.normcase(str(candidate))
            if key in seen_symlinks:
                raise RuntimeError("symlink loop")
            target = Path(os.readlink(candidate))
            target_path = (
                target
                if target.is_absolute()
                else candidate.parent / target
            )
            tail = Path(*parts[index + 1:]) if index + 1 < len(parts) else Path()
            return _resolve_path(
                target_path / tail,
                seen_symlinks=seen_symlinks | {key},
            )
        current = candidate
    return current


def resolve_g1_production_roots(
    repo_root: str | Path | None = None,
) -> tuple[Path, ...]:
    """Resolve all protected G1 roots below the real ``value-screener`` root."""
    base = Path(repo_root).expanduser().resolve() if repo_root else _default_repo_root()
    runtime_root = base / "value-screener"
    return tuple(
        _resolve_path(runtime_root.joinpath(*relative_path))
        for relative_path in _PRODUCTION_ROOT_RELATIVE_PATHS
    )


def _absolute_without_resolving(path: Path) -> Path:
    return Path.cwd() / path if not path.is_absolute() else path.absolute()


def _relation(candidate: Path, protected: Path) -> str | None:
    if candidate == protected:
        return "exact"
    if candidate.is_relative_to(protected):
        return "descendant"
    if protected.is_relative_to(candidate):
        return "ancestor"
    return None


def _first_violation(
    candidate: Path,
    protected_roots: Iterable[Path],
) -> tuple[Path, str] | None:
    lexical_candidate = _absolute_without_resolving(candidate)
    resolved_candidate = _resolve_path(candidate)
    for protected in protected_roots:
        lexical_protected = _absolute_without_resolving(protected)
        resolved_protected = protected.resolve()
        for candidate_path, protected_path in (
            (lexical_candidate, lexical_protected),
            (resolved_candidate, resolved_protected),
        ):
            relation = _relation(candidate_path, protected_path)
            if relation:
                return protected_path, relation
    return None


def validate_g1_output_root(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> Path:
    """Return a safe resolved output root or raise before any side effect."""
    candidate = Path(path).expanduser()
    try:
        violation = _first_violation(
            candidate,
            resolve_g1_production_roots(repo_root),
        )
        resolved_candidate = _resolve_path(candidate)
    except (OSError, RuntimeError) as exc:
        raise ProductionPathViolation(
            "G1 protected production output root rejected: relation=unresolvable"
        ) from exc
    if violation:
        _protected, relation = violation
        raise ProductionPathViolation(
            f"G1 protected production output root rejected: relation={relation}"
        )
    return resolved_candidate
