"""G2 identity/provenance audit chain.

This module deliberately owns only identity binding and evidence persistence.
It does not decide whether a thesis is good, complete, or capability-passing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from data.lib.identity import canonical_ticker

SCHEMA_VERSION = "g2-identity-audit-chain-v1"
ARTIFACT_TYPES = ("dossier", "prompt", "debate", "quality_report", "final_result")


class AuditIdentityError(ValueError):
    """Raised when an audit identity or provenance chain cannot be trusted."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AuditIdentityError("value is not strict JSON") from exc


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditIdentity:
    canonical_ticker: str
    run_id: str
    profile_version: str
    input_hash: str
    dossier_snapshot: str
    prompt_version: str
    model_configuration: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_identity_structure(self)
        if not isinstance(self.model_configuration, Mapping):
            raise AuditIdentityError("model_configuration is required")
        normalized = json.loads(_canonical_json(dict(self.model_configuration)))
        object.__setattr__(self, "model_configuration", normalized)

    @property
    def identity_digest(self) -> str:
        return payload_sha256(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditIdentityError(f"{name} is required")
    return value.strip()


def _validate_run_id(run_id: str) -> str:
    value = _require_text("run_id", run_id)
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise AuditIdentityError("run_id must be a relative path leaf")
    return value


def _validate_digest(name: str, value: Any) -> str:
    text = _require_text(name, value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise AuditIdentityError(f"{name} must be a lowercase sha256 digest")
    return text


def _validate_identity_structure(identity: AuditIdentity) -> None:
    try:
        canonical = canonical_ticker(identity.canonical_ticker)
    except (TypeError, ValueError) as exc:
        raise AuditIdentityError("identity ticker is not canonical") from exc
    if canonical != identity.canonical_ticker:
        raise AuditIdentityError("identity ticker is not canonical")
    _validate_run_id(identity.run_id)
    _require_text("profile_version", identity.profile_version)
    _validate_digest("input_hash", identity.input_hash)
    _require_text("dossier_snapshot", identity.dossier_snapshot)
    _require_text("prompt_version", identity.prompt_version)
    if not isinstance(identity.model_configuration, Mapping):
        raise AuditIdentityError("model_configuration is required")


def validate_audit_identity_structure(identity: AuditIdentity) -> None:
    """Validate supplied identity fields before callers construct any paths."""
    _validate_identity_structure(identity)


def _validate_dossier_ticker(
    dossier: Mapping[str, Any],
    canonical: str,
) -> None:
    found_ticker = False

    def validate_section(value: Any, location: str) -> None:
        nonlocal found_ticker
        if isinstance(value, Mapping):
            for key in ("ticker", "canonical_ticker", "symbol", "code"):
                if key not in value:
                    continue
                found_ticker = True
                declared = value[key]
                if not isinstance(declared, str) or not declared.strip():
                    raise AuditIdentityError(f"dossier ticker at {location}.{key} is invalid")
                try:
                    if canonical_ticker(declared) != canonical:
                        raise AuditIdentityError(
                            f"dossier ticker mismatch at {location}.{key}"
                        )
                except (TypeError, ValueError) as exc:
                    raise AuditIdentityError(
                        f"dossier ticker at {location}.{key} is not canonical"
                    ) from exc
            for key, child in value.items():
                if isinstance(child, (Mapping, list, tuple)):
                    validate_section(child, f"{location}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                validate_section(child, f"{location}[{index}]")

    validate_section(dossier, "dossier")
    if not found_ticker:
        raise AuditIdentityError("dossier ticker is required")


def _declared_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "ticker",
            "canonical_ticker",
            "run_id",
            "profile_version",
            "input_hash",
            "dossier_snapshot",
            "prompt_version",
            "model_configuration",
        )
        if key in payload
    }


def _assert_payload_identity(
    payload: Any,
    identity: AuditIdentity,
    *,
    require_complete: bool = False,
) -> None:
    if not isinstance(payload, Mapping):
        if require_complete:
            raise AuditIdentityError("artifact payload must be a mapping")
        return
    declared = _declared_identity(payload)
    required = {
        "run_id",
        "profile_version",
        "input_hash",
        "dossier_snapshot",
        "prompt_version",
        "model_configuration",
    }
    if require_complete:
        if "ticker" not in declared and "canonical_ticker" not in declared:
            raise AuditIdentityError("artifact payload ticker is required")
        missing = sorted(required - declared.keys())
        if missing:
            raise AuditIdentityError(
                f"artifact payload identity is incomplete: {', '.join(missing)}"
            )
    if "ticker" in declared:
        try:
            declared_ticker = canonical_ticker(declared["ticker"])
        except (TypeError, ValueError) as exc:
            raise AuditIdentityError("payload ticker is not canonical") from exc
        if declared_ticker != identity.canonical_ticker:
            raise AuditIdentityError(
                f"ticker mismatch: expected {identity.canonical_ticker}, got {declared_ticker}"
            )
    if "canonical_ticker" in declared and declared["canonical_ticker"] != identity.canonical_ticker:
        raise AuditIdentityError("canonical_ticker mismatch")
    for field in (
        "run_id",
        "profile_version",
        "input_hash",
        "dossier_snapshot",
        "prompt_version",
        "model_configuration",
    ):
        if field in declared and declared[field] != getattr(identity, field):
            raise AuditIdentityError(f"{field} mismatch")


def create_audit_identity(
    ticker: str,
    *,
    dossier: Mapping[str, Any],
    profile_version: str,
    prompt_version: str,
    model_configuration: Mapping[str, Any],
    run_id: str | None = None,
    input_hash: str | None = None,
    dossier_snapshot: str | None = None,
) -> AuditIdentity:
    """Create and validate the only identity context for an audited run."""
    try:
        canonical = canonical_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise AuditIdentityError(f"ticker is not canonical: {ticker!r}") from exc
    if not isinstance(dossier, Mapping) or not dossier:
        raise AuditIdentityError("dossier is required")
    _validate_dossier_ticker(dossier, canonical)
    normalized_run_id = _validate_run_id(run_id or str(uuid.uuid4()))
    normalized_snapshot = _require_text(
        "dossier_snapshot",
        dossier_snapshot or dossier.get("snapshot_version") or payload_sha256(dossier),
    )
    dossier_hash = payload_sha256(dossier)
    normalized_input_hash = _require_text("input_hash", input_hash or dossier_hash)
    if normalized_input_hash != dossier_hash:
        raise AuditIdentityError("input_hash must equal dossier payload hash")
    if not isinstance(model_configuration, Mapping):
        raise AuditIdentityError("model_configuration is required")
    identity = AuditIdentity(
        canonical_ticker=canonical,
        run_id=normalized_run_id,
        profile_version=_require_text("profile_version", profile_version),
        input_hash=normalized_input_hash,
        dossier_snapshot=normalized_snapshot,
        prompt_version=_require_text("prompt_version", prompt_version),
        model_configuration=dict(model_configuration),
    )
    _assert_payload_identity(dossier, identity)
    return identity


def validate_audit_identity(
    identity: AuditIdentity,
    *,
    ticker: str,
    dossier: Mapping[str, Any],
) -> None:
    """Ensure a caller-supplied identity belongs to this exact dossier input."""
    _validate_identity_structure(identity)
    try:
        canonical = canonical_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise AuditIdentityError("ticker is not canonical") from exc
    if identity.canonical_ticker != canonical:
        raise AuditIdentityError("identity ticker mismatch")
    _validate_dossier_ticker(dossier, canonical)
    if identity.input_hash != payload_sha256(dossier):
        raise AuditIdentityError("identity input_hash mismatch")
    _assert_payload_identity(dossier, identity)


def _identity_from_dict(value: Mapping[str, Any]) -> AuditIdentity:
    try:
        identity = AuditIdentity(
            canonical_ticker=value["canonical_ticker"],
            run_id=value["run_id"],
            profile_version=value["profile_version"],
            input_hash=value["input_hash"],
            dossier_snapshot=value["dossier_snapshot"],
            prompt_version=value["prompt_version"],
            model_configuration=dict(value["model_configuration"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditIdentityError("artifact identity is incomplete") from exc
    try:
        if canonical_ticker(identity.canonical_ticker) != identity.canonical_ticker:
            raise AuditIdentityError("artifact ticker is not canonical")
    except ValueError as exc:
        raise AuditIdentityError("artifact ticker is not canonical") from exc
    _validate_run_id(identity.run_id)
    return identity


@dataclass(frozen=True)
class AuditArtifact:
    artifact_type: str
    identity: AuditIdentity
    payload_sha256: str
    parent_hashes: tuple[str, ...]
    payload: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": self.artifact_type,
            "identity": self.identity.to_dict(),
            "payload_sha256": self.payload_sha256,
            "parent_hashes": list(self.parent_hashes),
            "payload": self.payload,
        }

    @property
    def artifact_hash(self) -> str:
        return payload_sha256(self.to_dict())


class AuditChainWriter:
    """Write a run-scoped, exclusive-create provenance chain."""

    def __init__(self, output_root: str | Path, identity: AuditIdentity):
        self.identity = identity
        validate_audit_identity_structure(identity)
        self.output_root = Path(output_root)
        self.run_root = self.output_root / identity.run_id
        self.staging_root = self.output_root / ".staging" / identity.run_id
        if self.run_root.exists() or self.staging_root.exists():
            raise FileExistsError(
                f"refusing to reuse audit run root: {self.run_root}"
            )
        self.staging_root.mkdir(parents=True, exist_ok=False)
        self._artifacts: list[AuditArtifact] = []

    def write(self, artifact_type: str, payload: Any) -> AuditArtifact:
        if artifact_type not in ARTIFACT_TYPES:
            raise AuditIdentityError(f"unknown artifact_type: {artifact_type}")
        _assert_payload_identity(payload, self.identity, require_complete=True)
        _validate_artifact_payload(artifact_type, payload, self.identity)
        if self._artifacts and ARTIFACT_TYPES[len(self._artifacts)] != artifact_type:
            raise AuditIdentityError(
                f"artifact order mismatch: expected {ARTIFACT_TYPES[len(self._artifacts)]}"
            )
        artifact = AuditArtifact(
            artifact_type=artifact_type,
            identity=self.identity,
            payload_sha256=payload_sha256(payload),
            parent_hashes=(
                (self._artifacts[-1].artifact_hash,) if self._artifacts else ()
            ),
            payload=payload,
        )
        path = self.staging_root / f"{len(self._artifacts) + 1:02d}-{artifact_type}.json"
        if path.exists():
            raise FileExistsError(f"refusing to overwrite audit artifact: {path}")
        with path.open("x", encoding="utf-8") as handle:
            json.dump(artifact.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self._artifacts.append(artifact)
        return artifact

    def finalize(self) -> dict[str, Any]:
        if len(self._artifacts) != len(ARTIFACT_TYPES):
            raise AuditIdentityError("audit chain is incomplete")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "identity": self.identity.to_dict(),
            "identity_digest": self.identity.identity_digest,
            "artifacts": [
                {
                    "artifact_type": artifact.artifact_type,
                    "path": f"{index:02d}-{artifact.artifact_type}.json",
                    "payload_sha256": artifact.payload_sha256,
                    "artifact_hash": artifact.artifact_hash,
                    "parent_hashes": list(artifact.parent_hashes),
                }
                for index, artifact in enumerate(self._artifacts, start=1)
            ],
        }
        manifest["manifest_sha256"] = payload_sha256(manifest)
        path = self.staging_root / "manifest.json"
        if path.exists():
            raise FileExistsError(f"refusing to overwrite audit manifest: {path}")
        with path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self.staging_root.rename(self.run_root)
        return manifest

    def abort(self) -> None:
        """Discard an unpublished staged run after an audited execution fails."""
        if self.staging_root.exists():
            shutil.rmtree(self.staging_root)
        if self.run_root.exists():
            shutil.rmtree(self.run_root)


def _validate_artifact_payload(
    artifact_type: str,
    payload: Mapping[str, Any],
    identity: AuditIdentity,
) -> None:
    """Reject an incomplete artifact before it can become part of a chain."""
    if artifact_type == "dossier":
        if "dossier" not in payload or "dossier_sha256" not in payload:
            raise AuditIdentityError("dossier artifact requires snapshot and hash")
        _validate_dossier_ticker(payload["dossier"], identity.canonical_ticker)
        dossier_hash = payload_sha256(payload["dossier"])
        if payload["dossier_sha256"] != dossier_hash:
            raise AuditIdentityError("dossier artifact hash mismatch")
        if dossier_hash != identity.input_hash:
            raise AuditIdentityError("dossier artifact does not match input_hash")
    elif artifact_type == "prompt":
        has_full_prompt = isinstance(payload.get("prompts"), list)
        has_single_prompt = "system_prompt" in payload and "user_message" in payload
        if not (has_full_prompt or has_single_prompt):
            raise AuditIdentityError("prompt artifact requires recorded prompt input")
        if has_full_prompt:
            prompts = payload["prompts"]
            if not prompts:
                raise AuditIdentityError("prompt artifact requires at least one prompt record")
            for prompt in prompts:
                if not isinstance(prompt, Mapping) or any(
                    not isinstance(prompt.get(field), str) or not prompt[field]
                    for field in ("agent", "stage", "round", "system_prompt", "user_message")
                ):
                    raise AuditIdentityError("prompt artifact contains an incomplete prompt record")
        if has_single_prompt:
            for field in ("system_prompt", "user_message"):
                if not isinstance(payload[field], str) or not payload[field]:
                    raise AuditIdentityError(f"prompt artifact {field} is required")
            _validate_declared_hash(
                payload,
                value=payload["system_prompt"],
                field="system_prompt_sha256",
                label="system prompt",
            )
            _validate_declared_hash(
                payload,
                value=payload["user_message"],
                field="user_message_sha256",
                label="user message",
            )
        expected_binding = payload_sha256(_prompt_binding_value(payload))
        if payload.get("prompt_binding_sha256") != expected_binding:
            raise AuditIdentityError("prompt binding hash mismatch")
    elif artifact_type == "debate":
        has_council_debate = "debate_text" in payload and "debate_text_sha256" in payload
        has_fallback_debate = all(
            field in payload
            for field in (
                "agent_id",
                "response",
                "agent_output",
                "response_sha256",
                "agent_output_sha256",
            )
        )
        if not (has_council_debate or has_fallback_debate):
            raise AuditIdentityError("debate artifact requires recorded debate evidence")
        if has_council_debate:
            if not isinstance(payload["debate_text"], str) or not payload["debate_text"]:
                raise AuditIdentityError("debate artifact requires recorded debate text")
            _validate_declared_hash(
                payload,
                value=payload["debate_text"],
                field="debate_text_sha256",
                label="debate text",
                required=True,
            )
        if has_fallback_debate:
            _validate_declared_hash(
                payload,
                value=payload["response"],
                field="response_sha256",
                label="fallback response",
                required=True,
            )
            _validate_declared_hash(
                payload,
                value=payload["agent_output"],
                field="agent_output_sha256",
                label="fallback agent output",
                required=True,
            )
            response = payload["response"]
            agent_output = payload["agent_output"]
            if response == "":
                if agent_output is not None:
                    raise AuditIdentityError("fallback response/output binding mismatch")
            else:
                try:
                    from council.schema import AgentOutput

                    parsed_output = AgentOutput.from_json(
                        payload["agent_id"], response
                    ).to_dict()
                except Exception as exc:
                    raise AuditIdentityError(
                        "fallback response cannot be parsed for binding"
                    ) from exc
                if parsed_output != agent_output:
                    raise AuditIdentityError("fallback response/output binding mismatch")
    elif artifact_type == "quality_report":
        if "quality_status" not in payload and "r1_quality_warnings" not in payload:
            raise AuditIdentityError("quality report requires a recorded quality status")
    elif artifact_type == "final_result":
        has_council_result = (
            "published_output" in payload and "published_output_sha256" in payload
        )
        has_fallback_result = "result" in payload and "result_sha256" in payload
        if not (has_council_result or has_fallback_result):
            raise AuditIdentityError("final result requires the published result payload")
        if has_council_result:
            _validate_nested_final_identity(
                payload["published_output"],
                identity,
                label="final result",
            )
            _validate_declared_hash(
                payload,
                value=payload["published_output"],
                field="published_output_sha256",
                label="published output",
                required=True,
            )
        if has_fallback_result:
            _validate_nested_final_identity(
                payload["result"],
                identity,
                label="final result",
            )
            _validate_declared_hash(
                payload,
                value=payload["result"],
                field="result_sha256",
                label="final result",
                required=True,
            )


def _validate_declared_hash(
    payload: Mapping[str, Any],
    *,
    value: Any,
    field: str,
    label: str,
    required: bool = False,
) -> None:
    if field not in payload:
        if required:
            raise AuditIdentityError(f"{label} hash is required")
        return
    if payload[field] != payload_sha256(value):
            raise AuditIdentityError(f"{label} hash mismatch")


def _validate_nested_final_identity(
    value: Any,
    identity: AuditIdentity,
    *,
    label: str,
) -> None:
    if not isinstance(value, Mapping):
        raise AuditIdentityError(f"{label} payload must be a mapping")
    try:
        _assert_payload_identity(value, identity, require_complete=True)
    except AuditIdentityError as exc:
        raise AuditIdentityError(f"{label} identity mismatch: {exc}") from exc


def _prompt_binding_value(payload: Mapping[str, Any]) -> dict[str, Any]:
    identity_fields = {
        field: payload[field]
        for field in (
            "ticker",
            "run_id",
            "profile_version",
            "input_hash",
            "dossier_snapshot",
            "prompt_version",
            "model_configuration",
        )
    }
    if isinstance(payload.get("prompts"), list):
        prompts = payload["prompts"]
    else:
        prompts = [
            {
                "agent": payload.get("agent_id", "fallback"),
                "stage": payload.get("prompt_stage", "fallback"),
                "round": payload.get("reasoning_level", "heavy"),
                "system_prompt": payload["system_prompt"],
                "user_message": payload["user_message"],
            }
        ]
    return {**identity_fields, "prompts": prompts}


def _validate_sha256_field(
    payload: Mapping[str, Any],
    field: str,
    label: str,
) -> None:
    value = payload.get(field)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AuditIdentityError(f"{label} hash is invalid")


def _load_artifact(path: Path) -> AuditArtifact:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise AuditIdentityError("unsupported audit schema")
        identity = _identity_from_dict(data["identity"])
        payload = data["payload"]
        expected_payload_hash = payload_sha256(payload)
        if data.get("payload_sha256") != expected_payload_hash:
            raise AuditIdentityError(f"payload hash mismatch: {path.name}")
        artifact = AuditArtifact(
            artifact_type=data["artifact_type"],
            identity=identity,
            payload_sha256=data["payload_sha256"],
            parent_hashes=tuple(data.get("parent_hashes") or ()),
            payload=payload,
        )
        if artifact.artifact_type not in ARTIFACT_TYPES:
            raise AuditIdentityError(f"unknown artifact type: {path.name}")
        if data.get("artifact_hash") and data["artifact_hash"] != artifact.artifact_hash:
            raise AuditIdentityError(f"artifact hash mismatch: {path.name}")
        return artifact
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        if isinstance(exc, AuditIdentityError):
            raise
        raise AuditIdentityError(f"invalid audit artifact: {path.name}") from exc


def verify_audit_chain(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise AuditIdentityError("audit manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = _identity_from_dict(manifest["identity"])
        if manifest.get("identity_digest") != identity.identity_digest:
            raise AuditIdentityError("identity digest mismatch")
        if not isinstance(manifest.get("generated_at"), str) or not manifest["generated_at"]:
            raise AuditIdentityError("manifest generated_at is required")
        expected_manifest_hash = manifest.get("manifest_sha256")
        unsigned_manifest = dict(manifest)
        unsigned_manifest.pop("manifest_sha256", None)
        if expected_manifest_hash != payload_sha256(unsigned_manifest):
            raise AuditIdentityError("manifest hash mismatch")
        entries = manifest["artifacts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AuditIdentityError("invalid audit manifest") from exc

    if [entry.get("artifact_type") for entry in entries] != list(ARTIFACT_TYPES):
        raise AuditIdentityError("manifest artifact order is invalid")
    previous_hash: str | None = None
    for index, entry in enumerate(entries, start=1):
        expected_name = f"{index:02d}-{ARTIFACT_TYPES[index - 1]}.json"
        entry_path = entry.get("path")
        if entry_path != expected_name:
            raise AuditIdentityError(f"manifest path mismatch: {entry_path!r}")
        path = root / expected_name
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise AuditIdentityError(f"unsafe artifact path: {path.name}")
        artifact = _load_artifact(path)
        if artifact.identity != identity:
            raise AuditIdentityError(f"identity mismatch: {path.name}")
        if artifact.artifact_type != entry["artifact_type"]:
            raise AuditIdentityError(f"manifest type mismatch: {path.name}")
        if artifact.payload_sha256 != entry.get("payload_sha256"):
            raise AuditIdentityError(f"manifest payload hash mismatch: {path.name}")
        if artifact.artifact_hash != entry.get("artifact_hash"):
            raise AuditIdentityError(f"manifest artifact hash mismatch: {path.name}")
        if artifact.parent_hashes != tuple(entry.get("parent_hashes") or ()):
            raise AuditIdentityError(f"manifest parent metadata mismatch: {path.name}")
        if artifact.parent_hashes != ((previous_hash,) if previous_hash else ()):
            raise AuditIdentityError(f"parent hash mismatch: {path.name}")
        _assert_payload_identity(artifact.payload, identity, require_complete=True)
        _validate_artifact_payload(artifact.artifact_type, artifact.payload, identity)
        if artifact.artifact_type == "final_result":
            final_payload = artifact.payload
            if "published_output" in final_payload and "published_output_sha256" in final_payload:
                if payload_sha256(final_payload["published_output"]) != final_payload[
                    "published_output_sha256"
                ]:
                    raise AuditIdentityError("published output hash mismatch")
            if "result" in final_payload and "result_sha256" in final_payload:
                if payload_sha256(final_payload["result"]) != final_payload["result_sha256"]:
                    raise AuditIdentityError("final result hash mismatch")
        if artifact.artifact_type == "debate":
            debate_payload = artifact.payload
            if "debate_text" in debate_payload and "debate_text_sha256" in debate_payload:
                if payload_sha256(debate_payload["debate_text"]) != debate_payload[
                    "debate_text_sha256"
                ]:
                    raise AuditIdentityError("debate text hash mismatch")
        if artifact.artifact_type == "dossier":
            dossier_payload = artifact.payload
            if "dossier" not in dossier_payload or "dossier_sha256" not in dossier_payload:
                raise AuditIdentityError("dossier snapshot is missing")
            dossier_hash = payload_sha256(dossier_payload["dossier"])
            if dossier_hash != dossier_payload["dossier_sha256"]:
                raise AuditIdentityError("dossier snapshot hash mismatch")
            if dossier_hash != identity.input_hash:
                raise AuditIdentityError("dossier snapshot does not match input_hash")
        previous_hash = artifact.artifact_hash
    return manifest
