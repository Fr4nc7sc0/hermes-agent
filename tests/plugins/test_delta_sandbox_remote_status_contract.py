"""RED contract for the Delta remote sandbox STATUS adapter.

Hermes core must remain generic.

The Delta-specific plugin will consume the generic
on_file_attachment_staged lifecycle event and may query
only /sandbox/status in this slice.

No real network request is performed by this test.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PLUGIN = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "__init__.py"
)

ATTACH_HOOK = "on_file_attachment_staged"

STATUS_ROUTE = "/sandbox/status"

REMOTE_SANDBOX_ID = "hermes-remote-primary"

BASE_URL_ENV = "DELTA_SANDBOX_REMOTE_BASE_URL"
TOKEN_FILE_ENV = "DELTA_SANDBOX_REMOTE_TOKEN_FILE"

FORBIDDEN_CAPABILITIES = (
    "/sandbox/ensure",
    "/sandbox/exec",
    "sandbox.ensure",
    "sandbox.exec",
)


def red(reason: str) -> int:
    print(
        "RED_EXPECTED="
        + reason
    )

    return 1


def main() -> int:
    if not PLUGIN.is_file():
        return red(
            "DELTA_SANDBOX_REMOTE_PLUGIN_MISSING"
        )

    source = PLUGIN.read_text(
        encoding="utf-8-sig"
    )

    required = (
        ATTACH_HOOK,
        STATUS_ROUTE,
        REMOTE_SANDBOX_ID,
        BASE_URL_ENV,
        TOKEN_FILE_ENV,
    )

    for item in required:
        if item not in source:
            return red(
                "REQUIRED_CONTRACT_TERM_MISSING:"
                + item
            )

    for forbidden in FORBIDDEN_CAPABILITIES:
        if forbidden in source:
            raise AssertionError(
                "forbidden capability present: "
                + forbidden
            )

    if "100.114.60.59" in source:
        raise AssertionError(
            "gateway address must not be hard-coded"
        )

    tree = ast.parse(
        source,
        filename=str(PLUGIN),
    )

    register_node = None

    for node in tree.body:
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and node.name == "register"
        ):
            register_node = node
            break

    if register_node is None:
        return red(
            "PLUGIN_REGISTER_FUNCTION_MISSING"
        )

    register_source = (
        ast.get_source_segment(
            source,
            register_node,
        )
        or ""
    )

    if "register_hook" not in register_source:
        return red(
            "REGISTER_HOOK_CALL_MISSING"
        )

    if ATTACH_HOOK not in register_source:
        return red(
            "ATTACHMENT_HOOK_NOT_WIRED"
        )

    print(
        "STATUS_ONLY_PLUGIN_CONTRACT=GREEN"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
