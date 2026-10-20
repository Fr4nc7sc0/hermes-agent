"""Delta remote sandbox lifecycle adapter.

This plugin consumes generic Hermes lifecycle facts while keeping Delta
transport and policy outside Hermes core.

Current capability slice: remote sandbox status observation only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


ATTACH_HOOK = "on_file_attachment_staged"

STATUS_ROUTE = "/sandbox/status"

REMOTE_SANDBOX_ID = "hermes-remote-primary"

BASE_URL_ENV = "DELTA_SANDBOX_REMOTE_BASE_URL"
TOKEN_FILE_ENV = "DELTA_SANDBOX_REMOTE_TOKEN_FILE"

DEFAULT_TIMEOUT_SECONDS = 5.0


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

    except (
        urllib_error.HTTPError,
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
        "on_file_attachment_staged",
        _on_file_attachment_staged,
    )
