"""Delta remote sandbox lifecycle adapter.

This plugin consumes generic Hermes lifecycle facts while keeping Delta
transport and policy outside Hermes core.

Current capability slice: remote sandbox status observation only.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


ATTACH_HOOK = "on_file_attachment_staged"
SESSION_START_HOOK = "on_session_start"

STATUS_ROUTE = "/sandbox/status"
ENSURE_ROUTE = "/sandbox/ensure"

REMOTE_SANDBOX_ID = "hermes-remote-primary"

BASE_URL_ENV = "DELTA_SANDBOX_REMOTE_BASE_URL"
TOKEN_FILE_ENV = "DELTA_SANDBOX_REMOTE_TOKEN_FILE"

DEFAULT_TIMEOUT_SECONDS = 5.0

_ensure_policy_lock = threading.Lock()


def _configured_transport() -> tuple[str, Path] | None:
    """Return explicit remote transport configuration or None."""

    base_url = os.getenv(
        BASE_URL_ENV,
        "",
    ).strip().rstrip("/")

    token_file_raw = os.getenv(
        TOKEN_FILE_ENV,
        "",
    ).strip()

    if not base_url or not token_file_raw:
        return None

    return (
        base_url,
        Path(token_file_raw),
    )


def _read_token(token_file: Path) -> str:
    """Read the bearer token without logging or exposing its value."""

    token = token_file.read_text(
        encoding="utf-8"
    ).strip()

    if not token:
        raise ValueError(
            "Delta remote token file is empty"
        )

    return token


class RemoteSandboxNotFound(RuntimeError):
    """The fixed remote sandbox is confirmed absent by the gateway."""


def _is_confirmed_remote_sandbox_absence(
    exc: urllib_error.HTTPError,
) -> bool:
    """Accept only the gateway's canonical 404 absence contract."""

    if exc.code != 404:
        return False

    try:
        raw = exc.read(
            65536
        )

        result = json.loads(
            raw.decode("utf-8")
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False

    if not isinstance(
        result,
        dict,
    ):
        return False

    return (
        result.get("ok") is False
        and result.get("service")
        == "delta-remote-gateway"
        and result.get("error")
        == "sandbox_not_found"
    )


def _query_remote_status(
    base_url: str,
    token_file: Path,
) -> dict[str, Any]:
    """Query the fixed remote sandbox status endpoint."""

    token = _read_token(
        token_file
    )

    payload = json.dumps(
        {
            "sandbox_id":
                REMOTE_SANDBOX_ID,
        },
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    request = urllib_request.Request(
        base_url + STATUS_ROUTE,
        data=payload,
        method="POST",
        headers={
            "Authorization":
                "Bearer " + token,
            "Content-Type":
                "application/json",
        },
    )

    try:
        with urllib_request.urlopen(
            request,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read(
                65536
            )

    except urllib_error.HTTPError as exc:
        if _is_confirmed_remote_sandbox_absence(
            exc
        ):
            raise RemoteSandboxNotFound(
                "Delta remote sandbox is absent"
            ) from exc

        raise RuntimeError(
            "Delta remote status request failed"
        ) from exc

    except (
        urllib_error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise RuntimeError(
            "Delta remote status request failed"
        ) from exc

    try:
        result = json.loads(
            raw.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Delta remote status response was invalid"
        ) from exc

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "Delta remote status response was not an object"
        )

    if result.get("ok") is not True:
        raise RuntimeError(
            "Delta remote status response was not successful"
        )

    if (
        result.get("sandbox_id")
        != REMOTE_SANDBOX_ID
    ):
        raise RuntimeError(
            "Delta remote status response sandbox identity mismatch"
        )

    return result


def _ensure_remote_sandbox(
    base_url: str,
    token_file: Path,
) -> dict[str, Any]:
    """Ensure only the fixed remote sandbox through the gateway."""

    token = _read_token(
        token_file
    )

    request = urllib_request.Request(
        base_url + ENSURE_ROUTE,
        data=b"{}",
        method="POST",
        headers={
            "Authorization":
                "Bearer " + token,
            "Content-Type":
                "application/json",
        },
    )

    try:
        with urllib_request.urlopen(
            request,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read(
                65536
            )

    except (
        urllib_error.HTTPError,
        urllib_error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise RuntimeError(
            "Delta remote ensure request failed"
        ) from exc

    try:
        result = json.loads(
            raw.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Delta remote ensure response was invalid"
        ) from exc

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "Delta remote ensure response was not an object"
        )

    if result.get("ok") is not True:
        raise RuntimeError(
            "Delta remote ensure response was not successful"
        )

    if (
        result.get("sandbox_id")
        != REMOTE_SANDBOX_ID
    ):
        raise RuntimeError(
            "Delta remote ensure response sandbox identity mismatch"
        )

    return result


def _on_session_start(
    **kwargs: Any,
) -> None:
    """Ensure the fixed sandbox only after confirmed remote absence."""

    # Hermes lifecycle facts are intentionally not used as
    # Delta authorization input. The remote identity is fixed.
    _ = kwargs

    configured = _configured_transport()

    if configured is None:
        return None

    base_url, token_file = configured

    # on_session_start can repeat for prompt recovery/rebuild.
    # Serialize status -> possible ensure so concurrent callbacks
    # in this process cannot both observe absence and mutate.
    with _ensure_policy_lock:
        try:
            _query_remote_status(
                base_url,
                token_file,
            )

        except RemoteSandboxNotFound:
            try:
                _ensure_remote_sandbox(
                    base_url,
                    token_file,
                )
            except Exception:
                # Lifecycle integration is fail-open. An ENSURE
                # failure cannot break the Hermes session.
                return None

        except Exception:
            # Gateway/broker/transport failures are not absence.
            # Never mutate on an ambiguous failure.
            return None

    return None


def _on_file_attachment_staged(
    **kwargs: Any,
) -> None:
    """Best-effort status observation at the attachment lifecycle boundary."""

    # Consume only lifecycle metadata. Attachment bytes are never handled here.
    _ = kwargs

    configured = _configured_transport()

    if configured is None:
        return None

    base_url, token_file = configured

    try:
        _query_remote_status(
            base_url,
            token_file,
        )
    except Exception:
        # This is an observer hook. Remote status failure must not break
        # attachment staging or alter the Hermes lifecycle.
        return None

    return None


def register(ctx: Any) -> None:
    """Register the Delta adapter on the generic Hermes lifecycle seam."""

    ctx.register_hook(
        ATTACH_HOOK,
        _on_file_attachment_staged,
    )

    ctx.register_hook(
        SESSION_START_HOOK,
        _on_session_start,
    )
