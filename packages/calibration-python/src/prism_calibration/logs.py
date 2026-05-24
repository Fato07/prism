"""Braintrust log/span observability for calibration and trader runtime operations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prism_calibration.braintrust_sync import braintrust_project

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BRAINTRUST_CONFIG = _REPO_ROOT / ".bt" / "config.json"
_BRAINTRUST_KEYCHAIN_SERVICE = "com.braintrust.bt.cli"


class LogObservabilityError(ValueError):
    """Raised when Braintrust log observability cannot be configured."""


def _braintrust_cli_context() -> dict[str, str] | None:
    """Return local Braintrust CLI context when it is available non-interactively."""
    if not _BRAINTRUST_CONFIG.is_file() or shutil.which("bt") is None:
        return None

    try:
        status = subprocess.run(
            ["bt", "status", "--json", "--no-input"],
            check=False,
            capture_output=True,
            cwd=_REPO_ROOT,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if status.returncode != 0:
        return None

    try:
        payload = json.loads(status.stdout)
    except json.JSONDecodeError:
        return None

    org = payload.get("org")
    profile = payload.get("profile")
    if not isinstance(org, str) or not org.strip():
        return None
    if not isinstance(profile, str) or not profile.strip():
        return None

    return {"org": org, "profile": profile}


def _braintrust_cli_access_token(profile: str) -> str | None:
    """Read the saved Braintrust CLI OAuth access token from the local keychain."""
    if sys.platform != "darwin" or shutil.which("security") is None:
        return None

    try:
        token = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                f"oauth_access::{profile}",
                "-s",
                _BRAINTRUST_KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    value = token.stdout.strip()
    if token.returncode != 0 or not value:
        return None

    return value


def resolve_braintrust_credentials() -> tuple[str | None, str | None]:
    """Resolve Braintrust credentials from env or local CLI auth state.

    Returns (api_key, org_name) tuple. Either or both may be None
    if credentials are unavailable.
    """
    api_key = os.environ.get("BRAINTRUST_API_KEY")
    org_name = os.environ.get("BRAINTRUST_ORG_NAME")
    if api_key:
        return api_key, org_name

    context = _braintrust_cli_context()
    if context is None:
        return None, None

    token = _braintrust_cli_access_token(context["profile"])
    if token is None:
        return None, None

    return token, org_name or context["org"]


class CalibrationLogger:
    """Braintrust logger wrapper for calibration corpus operations.

    Emits logs/spans for calibration runs (pilot build, prelabel, sync, eval)
    that are visible via Braintrust CLI or UI and carry provenance tags
    tying them back to specific slices, cases, and lineage.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        org_name: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._org_name = org_name
        self._logger: Any = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize the Braintrust logger lazily on first use."""
        if self._initialized:
            return
        self._initialized = True

        api_key = self._api_key
        org_name = self._org_name

        if api_key is None:
            resolved_key, resolved_org = resolve_braintrust_credentials()
            api_key = resolved_key
            org_name = org_name or resolved_org

        if api_key is None:
            return  # No credentials available — logging silently disabled

        try:
            import braintrust

            self._logger = braintrust.init_logger(
                project=braintrust_project(),
                api_key=api_key,
                org_name=org_name,
                set_current=False,
            )
        except Exception:
            self._logger = None

    @property
    def active(self) -> bool:
        """Whether Braintrust logging is active."""
        self._ensure_initialized()
        return self._logger is not None

    def log_operation(
        self,
        *,
        operation: str,
        slice_name: str | None = None,
        case_id: str | None = None,
        lineage_id: str | None = None,
        source_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        scores: dict[str, float] | None = None,
    ) -> str | None:
        """Log a calibration operation to Braintrust.

        Args:
            operation: Name of the operation (e.g., "pilot-build", "prelabel", "sync", "eval").
            slice_name: Target slice if applicable.
            case_id: Row/case identifier if applicable.
            lineage_id: Lineage group identifier if applicable.
            source_type: Source type (synthetic, mutated, real) if applicable.
            metadata: Additional metadata to attach.
            scores: Optional score dictionary for the operation.

        Returns:
            The Braintrust log event ID, or None if logging is not active.
        """
        self._ensure_initialized()
        if self._logger is None:
            return None

        tag_members: set[str] = {"calibration", operation}
        if slice_name is not None:
            tag_members.add(slice_name)
        if source_type is not None:
            tag_members.add(source_type)
        tags = sorted(tag_members)

        event_metadata: dict[str, Any] = {
            "operation": operation,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if slice_name is not None:
            event_metadata["slice_name"] = slice_name
        if case_id is not None:
            event_metadata["case_id"] = case_id
        if lineage_id is not None:
            event_metadata["lineage_id"] = lineage_id
        if source_type is not None:
            event_metadata["source_type"] = source_type
        if metadata:
            event_metadata.update(metadata)

        event_id = self._logger.log(
            input={
                "operation": operation,
                "slice_name": slice_name,
                "case_id": case_id,
                "lineage_id": lineage_id,
                "source_type": source_type,
            },
            metadata=event_metadata,
            tags=tags,
            scores=scores,
        )

        return str(event_id) if event_id else None

    @contextmanager
    def span(
        self,
        *,
        name: str,
        operation: str,
        slice_name: str | None = None,
        case_id: str | None = None,
        lineage_id: str | None = None,
        source_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Create a Braintrust span for a calibration operation.

        The span carries provenance tags so it can be tied back to
        a specific slice, case, or lineage.

        Args:
            name: Span name (e.g., "prism.calibration.pilot-build").
            operation: Operation type (e.g., "pilot-build", "eval").
            slice_name: Target slice if applicable.
            case_id: Row/case identifier if applicable.
            lineage_id: Lineage group identifier if applicable.
            source_type: Source type if applicable.
            metadata: Additional metadata to attach.

        Yields:
            A Braintrust Span object, or a no-op span if logging is inactive.
        """
        self._ensure_initialized()

        span_metadata: dict[str, Any] = {
            "operation": operation,
        }
        if slice_name is not None:
            span_metadata["slice_name"] = slice_name
        if case_id is not None:
            span_metadata["case_id"] = case_id
        if lineage_id is not None:
            span_metadata["lineage_id"] = lineage_id
        if source_type is not None:
            span_metadata["source_type"] = source_type
        if metadata:
            span_metadata.update(metadata)

        if self._logger is not None:
            try:
                span_tag_members: set[str] = {"calibration", operation}
                if slice_name is not None:
                    span_tag_members.add(slice_name)
                if source_type is not None:
                    span_tag_members.add(source_type)

                span_obj = self._logger.start_span(
                    name=name,
                    span_attributes=span_metadata,
                    input={
                        "operation": operation,
                        "slice_name": slice_name,
                        "case_id": case_id,
                        "lineage_id": lineage_id,
                        "source_type": source_type,
                    },
                    tags=sorted(span_tag_members - {None}),
                )
                try:
                    yield span_obj
                finally:
                    span_obj.end()
                    self._logger.flush()
            except Exception:
                # If span creation fails, yield a no-op context
                yield None
        else:
            yield None

    def flush(self) -> None:
        """Flush any pending log events to Braintrust."""
        self._ensure_initialized()
        if self._logger is not None:
            with suppress(Exception):
                self._logger.flush()


def emit_trader_runtime_log(
    *,
    trace_id: str,
    market_id: str,
    action: str,
    final_probability: float,
    size_usdc: float,
    model_family: str,
    model_name: str,
    slice_name: str | None = None,
    case_id: str | None = None,
    lineage_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Emit a Braintrust log entry for a trader runtime generation.

    This creates a visible log entry in the Prism project that carries
    enough provenance tags to tie it back to a specific slice, case,
    or calibration context.

    Args:
        trace_id: The generated trace identifier.
        market_id: The target market ID.
        action: Trade action (BUY, SELL, HOLD).
        final_probability: Final probability estimate.
        size_usdc: Trade size in USDC.
        model_family: LLM model family (e.g., anthropic-claude).
        model_name: Specific model name.
        slice_name: Calibration slice if tied to a calibration run.
        case_id: Calibration case ID if applicable.
        lineage_id: Lineage group ID if applicable.
        metadata: Additional metadata.

    Returns:
        The log event ID, or None if logging is not active.
    """
    logger = CalibrationLogger()

    event_metadata: dict[str, Any] = {
        "trace_id": trace_id,
        "market_id": market_id,
        "model_family": model_family,
        "model_name": model_name,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if slice_name is not None:
        event_metadata["slice_name"] = slice_name
    if case_id is not None:
        event_metadata["case_id"] = case_id
    if lineage_id is not None:
        event_metadata["lineage_id"] = lineage_id
    if metadata:
        event_metadata.update(metadata)

    return logger.log_operation(
        operation="trader-generation",
        slice_name=slice_name,
        case_id=case_id,
        lineage_id=lineage_id,
        source_type="real",
        metadata=event_metadata,
    )


def emit_calibration_eval_log(
    *,
    eval_id: str,
    experiment_name: str,
    slice_name: str,
    export_id: str,
    evaluator_name: str,
    total_rows: int,
    passed_rows: int,
    failed_rows: int,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Emit a Braintrust log entry for a calibration eval run.

    This creates a visible log entry that can be discovered alongside
    the Braintrust experiment, carrying the eval identity and pass/fail
    summary so it can be correlated with the experiment and tied back
    to the frozen local export.

    Args:
        eval_id: Eval result identity.
        experiment_name: Braintrust experiment name.
        slice_name: Target slice.
        export_id: Frozen export identity.
        evaluator_name: Evaluator configuration name.
        total_rows: Total rows evaluated.
        passed_rows: Rows that passed.
        failed_rows: Rows that failed.
        metadata: Additional metadata.

    Returns:
        The log event ID, or None if logging is not active.
    """
    logger = CalibrationLogger()

    scores: dict[str, float] = {
        "pass_rate": round(passed_rows / max(total_rows, 1), 4),
    }

    event_metadata: dict[str, Any] = {
        "eval_id": eval_id,
        "experiment_name": experiment_name,
        "export_id": export_id,
        "evaluator_name": evaluator_name,
        "total_rows": total_rows,
        "passed_rows": passed_rows,
        "failed_rows": failed_rows,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if metadata:
        event_metadata.update(metadata)

    return logger.log_operation(
        operation="calibration-eval",
        slice_name=slice_name,
        metadata=event_metadata,
        scores=scores,
    )
