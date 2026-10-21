"""TRUE RED contract for Delta remote sandbox ENSURE transport.

No real network traffic is allowed.

Production contract:
- POST exactly to /sandbox/ensure;
- request JSON must be exactly {};
- gateway owns the fixed tenant/sandbox/task identity;
- Bearer authentication is required;
- Content-Type is application/json;
- timeout remains bounded;
- successful response must identify the fixed remote sandbox;
- sandbox.exec remains absent.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PLUGIN = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "__init__.py"
)

EXPECTED_SANDBOX_ID = (
    "hermes-remote-primary"
)

BASE_URL = (
    "http://gateway.invalid:8765"
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
        "h6_r35_delta_sandbox_remote",
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


class FakeResponse:
    def __init__(
        self,
        payload,
    ):
        self._raw = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def read(
        self,
        limit=-1,
    ):
        if (
            limit is None
            or limit < 0
        ):
            return self._raw

        return self._raw[:limit]


def header_map(
    request,
):
    return {
        key.lower(): value
        for key, value
        in request.header_items()
    }


def main() -> int:
    source = PLUGIN.read_text(
        encoding="utf-8-sig"
    )

    if (
        "/sandbox/exec"
        in source
        or "sandbox.exec"
        in source
    ):
        raise AssertionError(
            "sandbox.exec must remain absent"
        )

    if "/sandbox/ensure" not in source:
        return red(
            "REMOTE_ENSURE_ROUTE_MISSING"
        )

    module = load_plugin()

    if not hasattr(
        module,
        "ENSURE_ROUTE",
    ):
        return red(
            "REMOTE_ENSURE_CONSTANT_MISSING"
        )

    if (
        module.ENSURE_ROUTE
        != "/sandbox/ensure"
    ):
        raise AssertionError(
            "unexpected ENSURE route"
        )

    if not hasattr(
        module,
        "_ensure_remote_sandbox",
    ):
        return red(
            "REMOTE_ENSURE_FUNCTION_MISSING"
        )

    valid_payload = {
        "ok": True,
        "service": "delta-remote-gateway",
        "sandbox_id":
            EXPECTED_SANDBOX_ID,
    }

    calls = []

    def valid_urlopen(
        request,
        timeout=None,
    ):
        calls.append(
            (
                request,
                timeout,
            )
        )

        return FakeResponse(
            valid_payload
        )

    original = (
        module
        .urllib_request
        .urlopen
    )

    with tempfile.TemporaryDirectory(
        prefix="h6-r35-"
    ) as tmp:
        token_file = (
            Path(tmp)
            / "token"
        )

        token_file.write_text(
            "synthetic-unit-token\n",
            encoding="utf-8",
        )

        module.urllib_request.urlopen = (
            valid_urlopen
        )

        try:
            result = (
                module
                ._ensure_remote_sandbox(
                    BASE_URL,
                    token_file,
                )
            )
        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert result == valid_payload

        assert len(calls) == 1

        request, timeout = calls[0]

        assert (
            request.full_url
            == BASE_URL
            + "/sandbox/ensure"
        )

        assert (
            request.get_method()
            == "POST"
        )

        assert (
            json.loads(
                request.data.decode(
                    "utf-8"
                )
            )
            == {}
        )

        assert request.data == b"{}"

        headers = header_map(
            request
        )

        assert (
            headers.get(
                "authorization"
            )
            == "Bearer synthetic-unit-token"
        )

        assert (
            headers.get(
                "content-type"
            )
            == "application/json"
        )

        assert (
            timeout
            == module.DEFAULT_TIMEOUT_SECONDS
        )

        print(
            "ENSURE_MOCKED_HTTP_REQUEST_CONTRACT=PASS"
        )

        print(
            "ENSURE_REQUEST_BODY_EMPTY_OBJECT=PASS"
        )

        print(
            "REAL_NETWORK_CALL_COUNT=0"
        )


        mismatch_payload = {
            "ok": True,
            "service": "delta-remote-gateway",
            "sandbox_id":
                "unexpected-sandbox",
        }

        mismatch_calls = []

        def mismatch_urlopen(
            request,
            timeout=None,
        ):
            mismatch_calls.append(
                (
                    request,
                    timeout,
                )
            )

            return FakeResponse(
                mismatch_payload
            )

        module.urllib_request.urlopen = (
            mismatch_urlopen
        )

        try:
            rejected = False

            try:
                module._ensure_remote_sandbox(
                    BASE_URL,
                    token_file,
                )

            except RuntimeError:
                rejected = True

        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert len(
            mismatch_calls
        ) == 1

        if not rejected:
            return red(
                "ENSURE_RESPONSE_IDENTITY_NOT_VALIDATED"
            )


        failed_payload = {
            "ok": False,
            "service": "delta-remote-gateway",
        }

        failed_calls = []

        def failed_urlopen(
            request,
            timeout=None,
        ):
            failed_calls.append(
                (
                    request,
                    timeout,
                )
            )

            return FakeResponse(
                failed_payload
            )

        module.urllib_request.urlopen = (
            failed_urlopen
        )

        try:
            rejected = False

            try:
                module._ensure_remote_sandbox(
                    BASE_URL,
                    token_file,
                )

            except RuntimeError:
                rejected = True

        finally:
            module.urllib_request.urlopen = (
                original
            )

        assert len(
            failed_calls
        ) == 1

        if not rejected:
            return red(
                "ENSURE_UNSUCCESSFUL_RESPONSE_ACCEPTED"
            )


    print(
        "ENSURE_RESPONSE_VALIDATION=GREEN"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
