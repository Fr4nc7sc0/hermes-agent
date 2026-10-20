"""HTTP contract for the Delta remote STATUS adapter.

No real network traffic is allowed.

The adapter must:
- POST exactly to /sandbox/status;
- send only the fixed sandbox id;
- use Bearer authentication;
- use application/json;
- preserve its bounded timeout;
- reject a successful HTTP response that does not describe the
  fixed remote sandbox identity.
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

EXPECTED_SANDBOX_ID = "hermes-remote-primary"

BASE_URL = "http://gateway.invalid:8765"


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "h6_r6_delta_sandbox_remote",
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
        if limit is None or limit < 0:
            return self._raw

        return self._raw[:limit]


def header_map(request):
    return {
        key.lower(): value
        for key, value
        in request.header_items()
    }


def main() -> int:
    module = load_plugin()

    calls = []

    valid_payload = {
        "ok": True,
        "service": "delta-remote-gateway",
        "sandbox_id": EXPECTED_SANDBOX_ID,
        "state": "running",
    }

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

    original = module.urllib_request.urlopen

    with tempfile.TemporaryDirectory(
        prefix="h6-r6-"
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
                module._query_remote_status(
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
            + "/sandbox/status"
        )

        assert (
            request.get_method()
            == "POST"
        )

        assert json.loads(
            request.data.decode(
                "utf-8"
            )
        ) == {
            "sandbox_id":
                EXPECTED_SANDBOX_ID,
        }

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
            "MOCKED_HTTP_REQUEST_CONTRACT=PASS"
        )

        print(
            "REAL_NETWORK_CALL_COUNT=0"
        )

        mismatch_payload = {
            "ok": True,
            "service": "delta-remote-gateway",
            "sandbox_id":
                "unexpected-sandbox",
            "state": "running",
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
                module._query_remote_status(
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
            print(
                "RED_EXPECTED="
                "STATUS_RESPONSE_IDENTITY_NOT_VALIDATED"
            )

            return 1

        print(
            "STATUS_RESPONSE_IDENTITY_VALIDATION=GREEN"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
