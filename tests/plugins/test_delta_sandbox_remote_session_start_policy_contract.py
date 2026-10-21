"""TRUE RED contract for Delta remote sandbox lifecycle ensure policy.

No real network traffic is allowed.

Policy:
- lifecycle seam is generic Hermes on_session_start;
- unconfigured transport performs nothing;
- configured session start always checks STATUS first;
- healthy STATUS never calls ENSURE;
- only RemoteSandboxNotFound authorizes ENSURE;
- generic status/infrastructure failure never calls ENSURE;
- ENSURE failure is fail-open to Hermes;
- concurrent session-start callbacks in one process must serialize
  status->ensure so confirmed absence cannot produce duplicate ENSURE;
- sandbox.exec remains absent.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PLUGIN = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "__init__.py"
)

MANIFEST = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "plugin.yaml"
)

SESSION_START_HOOK = "on_session_start"

ATTACH_HOOK = "on_file_attachment_staged"

BASE_URL = "http://gateway.invalid:8765"

TOKEN_FILE = Path(
    "/synthetic/token"
)

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
        "h6_r41_delta_sandbox_remote",
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


class FakeContext:
    def __init__(self):
        self.hooks = []

    def register_hook(
        self,
        name,
        callback,
    ):
        self.hooks.append(
            (
                name,
                callback,
            )
        )


def main() -> int:
    source = PLUGIN.read_text(
        encoding="utf-8-sig"
    )

    if (
        "/sandbox/exec" in source
        or "sandbox.exec" in source
    ):
        raise AssertionError(
            "sandbox.exec must remain absent"
        )

    module = load_plugin()


    if not hasattr(
        module,
        "SESSION_START_HOOK",
    ):
        return red(
            "SESSION_START_HOOK_MISSING"
        )

    if (
        module.SESSION_START_HOOK
        != SESSION_START_HOOK
    ):
        raise AssertionError(
            "unexpected session-start hook name"
        )


    if not hasattr(
        module,
        "_on_session_start",
    ):
        return red(
            "SESSION_START_CALLBACK_MISSING"
        )


    if not hasattr(
        module,
        "_ensure_policy_lock",
    ):
        return red(
            "ENSURE_POLICY_LOCK_MISSING"
        )


    manifest = MANIFEST.read_text(
        encoding="utf-8-sig"
    )

    if SESSION_START_HOOK not in manifest:
        return red(
            "SESSION_START_MANIFEST_DECLARATION_MISSING"
        )


    ctx = FakeContext()

    module.register(
        ctx
    )

    hook_names = [
        name
        for name, _callback
        in ctx.hooks
    ]

    if hook_names.count(
        ATTACH_HOOK
    ) != 1:
        raise AssertionError(
            "attachment hook registration changed"
        )

    if hook_names.count(
        SESSION_START_HOOK
    ) != 1:
        return red(
            "SESSION_START_HOOK_NOT_REGISTERED"
        )


    original_configured = (
        module._configured_transport
    )

    original_status = (
        module._query_remote_status
    )

    original_ensure = (
        module._ensure_remote_sandbox
    )


    try:

        # ----------------------------------------
        # Unconfigured transport: no network policy.
        # ----------------------------------------

        calls = []

        module._configured_transport = (
            lambda: None
        )

        module._query_remote_status = (
            lambda *args, **kwargs:
                calls.append("status")
        )

        module._ensure_remote_sandbox = (
            lambda *args, **kwargs:
                calls.append("ensure")
        )

        result = module._on_session_start(
            session_id="session-unconfigured",
            model="synthetic",
            platform="test",
        )

        assert result is None
        assert calls == []

        print(
            "UNCONFIGURED_SESSION_START_NOOP=PASS"
        )


        # ----------------------------------------
        # Healthy sandbox: STATUS only.
        # ----------------------------------------

        module._configured_transport = (
            lambda: (
                BASE_URL,
                TOKEN_FILE,
            )
        )

        healthy_calls = []

        def healthy_status(
            base_url,
            token_file,
        ):
            healthy_calls.append(
                "status"
            )

            return {
                "ok": True,
                "service":
                    "delta-remote-gateway",
                "sandbox_id":
                    EXPECTED_SANDBOX_ID,
                "state": "running",
            }

        def forbidden_ensure(
            base_url,
            token_file,
        ):
            healthy_calls.append(
                "ensure"
            )

            raise AssertionError(
                "ensure called for healthy sandbox"
            )

        module._query_remote_status = (
            healthy_status
        )

        module._ensure_remote_sandbox = (
            forbidden_ensure
        )

        result = module._on_session_start(
            session_id="session-healthy",
            model="synthetic",
            platform="test",
        )

        assert result is None
        assert healthy_calls == [
            "status"
        ]

        print(
            "HEALTHY_STATUS_DOES_NOT_ENSURE=PASS"
        )


        # ----------------------------------------
        # Confirmed absence: exactly one ENSURE.
        # ----------------------------------------

        absent_calls = []

        def absent_status(
            base_url,
            token_file,
        ):
            absent_calls.append(
                "status"
            )

            raise module.RemoteSandboxNotFound(
                "synthetic absence"
            )

        def expected_ensure(
            base_url,
            token_file,
        ):
            absent_calls.append(
                "ensure"
            )

            return {
                "ok": True,
                "service":
                    "delta-remote-gateway",
                "sandbox_id":
                    EXPECTED_SANDBOX_ID,
            }

        module._query_remote_status = (
            absent_status
        )

        module._ensure_remote_sandbox = (
            expected_ensure
        )

        result = module._on_session_start(
            session_id="session-absent",
            model="synthetic",
            platform="test",
        )

        assert result is None

        assert absent_calls == [
            "status",
            "ensure",
        ]

        print(
            "CONFIRMED_ABSENCE_ENSURES_EXACTLY_ONCE=PASS"
        )


        # ----------------------------------------
        # Infrastructure/status failure:
        # never mutate.
        # ----------------------------------------

        infra_calls = []

        def infra_status(
            base_url,
            token_file,
        ):
            infra_calls.append(
                "status"
            )

            raise RuntimeError(
                "synthetic infrastructure failure"
            )

        def infra_forbidden_ensure(
            base_url,
            token_file,
        ):
            infra_calls.append(
                "ensure"
            )

            raise AssertionError(
                "ensure called after infra failure"
            )

        module._query_remote_status = (
            infra_status
        )

        module._ensure_remote_sandbox = (
            infra_forbidden_ensure
        )

        result = module._on_session_start(
            session_id="session-infra",
            model="synthetic",
            platform="test",
        )

        assert result is None

        assert infra_calls == [
            "status"
        ]

        print(
            "INFRA_FAILURE_NEVER_ENSURES=PASS"
        )


        # ----------------------------------------
        # Ensure failure itself is fail-open.
        # ----------------------------------------

        ensure_failure_calls = []

        def missing_status(
            base_url,
            token_file,
        ):
            ensure_failure_calls.append(
                "status"
            )

            raise module.RemoteSandboxNotFound(
                "synthetic absence"
            )

        def failing_ensure(
            base_url,
            token_file,
        ):
            ensure_failure_calls.append(
                "ensure"
            )

            raise RuntimeError(
                "synthetic ensure failure"
            )

        module._query_remote_status = (
            missing_status
        )

        module._ensure_remote_sandbox = (
            failing_ensure
        )

        result = module._on_session_start(
            session_id="session-ensure-fail",
            model="synthetic",
            platform="test",
        )

        assert result is None

        assert ensure_failure_calls == [
            "status",
            "ensure",
        ]

        print(
            "ENSURE_FAILURE_FAILS_OPEN=PASS"
        )


        # ----------------------------------------
        # Concurrency contract.
        #
        # Thread 1 sees absence and begins ensure.
        # Thread 2 starts while ensure is in flight.
        #
        # Correct serialization:
        #   T1 status -> ensure -> present
        #   T2 status -> healthy
        #
        # Therefore only ONE ensure occurs.
        # ----------------------------------------

        state_lock = threading.Lock()

        present = {
            "value": False,
        }

        status_calls = {
            "count": 0,
        }

        ensure_calls = {
            "count": 0,
        }

        ensure_entered = (
            threading.Event()
        )

        failures = []


        def concurrent_status(
            base_url,
            token_file,
        ):
            with state_lock:
                status_calls[
                    "count"
                ] += 1

                exists = present[
                    "value"
                ]

            if exists:
                return {
                    "ok": True,
                    "service":
                        "delta-remote-gateway",
                    "sandbox_id":
                        EXPECTED_SANDBOX_ID,
                    "state": "running",
                }

            raise module.RemoteSandboxNotFound(
                "synthetic concurrent absence"
            )


        def concurrent_ensure(
            base_url,
            token_file,
        ):
            with state_lock:
                ensure_calls[
                    "count"
                ] += 1

            ensure_entered.set()

            # Hold the mutation window open long enough
            # for thread 2 to race if policy is unlocked.
            time.sleep(
                0.15
            )

            with state_lock:
                present[
                    "value"
                ] = True

            return {
                "ok": True,
                "service":
                    "delta-remote-gateway",
                "sandbox_id":
                    EXPECTED_SANDBOX_ID,
            }


        module._query_remote_status = (
            concurrent_status
        )

        module._ensure_remote_sandbox = (
            concurrent_ensure
        )


        def run_session(
            session_id,
        ):
            try:
                module._on_session_start(
                    session_id=session_id,
                    model="synthetic",
                    platform="test",
                )

            except BaseException as exc:
                failures.append(
                    exc
                )


        first = threading.Thread(
            target=run_session,
            args=(
                "session-concurrent-1",
            ),
        )

        first.start()

        if not ensure_entered.wait(
            timeout=2.0
        ):
            raise AssertionError(
                "first ensure did not begin"
            )

        second = threading.Thread(
            target=run_session,
            args=(
                "session-concurrent-2",
            ),
        )

        second.start()

        first.join(
            timeout=3.0
        )

        second.join(
            timeout=3.0
        )

        if first.is_alive():
            raise AssertionError(
                "first policy worker hung"
            )

        if second.is_alive():
            raise AssertionError(
                "second policy worker hung"
            )

        if failures:
            raise failures[0]

        assert status_calls[
            "count"
        ] == 2

        if ensure_calls[
            "count"
        ] != 1:
            return red(
                "CONCURRENT_SESSION_START_DUPLICATE_ENSURE"
            )

        print(
            "CONCURRENT_SESSION_START_SERIALIZED=PASS"
        )

        print(
            "CONCURRENT_STATUS_CALL_COUNT=2"
        )

        print(
            "CONCURRENT_ENSURE_CALL_COUNT=1"
        )


    finally:

        module._configured_transport = (
            original_configured
        )

        module._query_remote_status = (
            original_status
        )

        module._ensure_remote_sandbox = (
            original_ensure
        )


    print(
        "SESSION_START_STATUS_BEFORE_ENSURE_POLICY=GREEN"
    )

    print(
        "REAL_NETWORK_CALL_COUNT=0"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
