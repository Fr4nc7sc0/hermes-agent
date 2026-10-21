"""TRUE RED contract for remote sandbox STATUS absence semantics.

No real network traffic is allowed.

The gateway contract distinguishes:

404
{"ok": false, "service": "delta-remote-gateway",
 "error": "sandbox_not_found"}

from infrastructure failures such as 502.

Hermes must preserve that distinction so lifecycle policy may call
ENSURE only for confirmed absence, never for gateway/broker failure.
"""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
from pathlib import Path
from urllib.error import HTTPError


REPO = Path(__file__).resolve().parents[2]

PLUGIN = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "__init__.py"
)

BASE_URL = "http://gateway.invalid:8765"

EXPECTED_SANDBOX_ID = (
    "hermes-remote-primary"
)


def red(
    reason: str,
) -> int:
    print(
        "RED_EXPECTED="
        + reason
    )

    return 1


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "h6_r39_delta_sandbox_remote",
        PLUGIN,
    )

    if spec is None or spec.loader is None:
        raise AssertionError(
            "plugin import spec unavailable"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


def http_error(
    status: int,
    payload: dict,
) -> HTTPError:

    raw = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    return HTTPError(
        BASE_URL + "/sandbox/status",
        status,
        "synthetic",
        hdrs=None,
        fp=io.BytesIO(raw),
    )


def main() -> int:
    module = load_plugin()

    if not hasattr(
        module,
        "RemoteSandboxNotFound",
    ):
        return red(
            "REMOTE_STATUS_NOT_FOUND_SIGNAL_MISSING"
        )

    absence_type = (
        module.RemoteSandboxNotFound
    )

    if not issubclass(
        absence_type,
        RuntimeError,
    ):
        raise AssertionError(
            "RemoteSandboxNotFound must subclass RuntimeError"
        )


    with tempfile.TemporaryDirectory(
        prefix="h6-r39-"
    ) as tmp:

        token_file = (
            Path(tmp)
            / "token"
        )

        token_file.write_text(
            "synthetic-unit-token\n",
            encoding="utf-8",
        )


        # ----------------------------------------
        # 404 + exact sandbox_not_found
        # must become the dedicated absence signal.
        # ----------------------------------------

        missing_calls = []

        def missing_urlopen(
            request,
            timeout=None,
        ):
            missing_calls.append(
                (
                    request,
                    timeout,
                )
            )

            raise http_error(
                404,
                {
                    "ok": False,
                    "service":
                        "delta-remote-gateway",
                    "error":
                        "sandbox_not_found",
                },
            )

        original = (
            module
            .urllib_request
            .urlopen
        )

        module.urllib_request.urlopen = (
            missing_urlopen
        )

        try:
            missing_signalled = False

            try:
                module._query_remote_status(
                    BASE_URL,
                    token_file,
                )

            except absence_type:
                missing_signalled = True

        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert len(missing_calls) == 1

        if not missing_signalled:
            return red(
                "REMOTE_STATUS_404_NOT_DISTINGUISHED"
            )


        # ----------------------------------------
        # 502 infrastructure failure must remain
        # generic failure, never "not found".
        # ----------------------------------------

        infra_calls = []

        def infra_urlopen(
            request,
            timeout=None,
        ):
            infra_calls.append(
                (
                    request,
                    timeout,
                )
            )

            raise http_error(
                502,
                {
                    "ok": False,
                    "service":
                        "delta-remote-gateway",
                    "broker":
                        "unavailable",
                },
            )

        module.urllib_request.urlopen = (
            infra_urlopen
        )

        try:
            generic_failed = False
            false_absence = False

            try:
                module._query_remote_status(
                    BASE_URL,
                    token_file,
                )

            except absence_type:
                false_absence = True

            except RuntimeError:
                generic_failed = True

        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert len(infra_calls) == 1

        if false_absence:
            raise AssertionError(
                "502 infrastructure failure "
                "misclassified as sandbox absence"
            )

        if not generic_failed:
            return red(
                "REMOTE_STATUS_502_NOT_FAILED"
            )


        # ----------------------------------------
        # A noncanonical 404 must not authorize
        # absence either.
        # ----------------------------------------

        other_404_calls = []

        def other_404_urlopen(
            request,
            timeout=None,
        ):
            other_404_calls.append(
                (
                    request,
                    timeout,
                )
            )

            raise http_error(
                404,
                {
                    "ok": False,
                    "service":
                        "delta-remote-gateway",
                    "error":
                        "different_error",
                },
            )

        module.urllib_request.urlopen = (
            other_404_urlopen
        )

        try:
            generic_failed = False
            false_absence = False

            try:
                module._query_remote_status(
                    BASE_URL,
                    token_file,
                )

            except absence_type:
                false_absence = True

            except RuntimeError:
                generic_failed = True

        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert len(
            other_404_calls
        ) == 1

        if false_absence:
            raise AssertionError(
                "noncanonical 404 misclassified "
                "as sandbox absence"
            )

        if not generic_failed:
            return red(
                "REMOTE_STATUS_NONCANONICAL_404_NOT_FAILED"
            )


    print(
        "STATUS_CONFIRMED_ABSENCE_SIGNAL=GREEN"
    )

    print(
        "STATUS_INFRA_FAILURE_REMAINS_GENERIC=GREEN"
    )

    print(
        "STATUS_NONCANONICAL_404_REMAINS_GENERIC=GREEN"
    )

    print(
        "REAL_NETWORK_CALL_COUNT=0"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
