"""Trusted attachment lifecycle hook contracts.

These tests intentionally describe the generic Hermes-side integration
surface required by the Delta sandbox attachment bridge.

Hermes owns lifecycle facts only.  There must be no Delta-specific import,
policy, capability format, broker knowledge, or sandbox behavior here.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PLUGINS = REPO / "hermes_cli" / "plugins.py"
METHODS_PROMPT = REPO / "tui_gateway" / "methods_prompt.py"
SERVER = REPO / "tui_gateway" / "server.py"


ATTACH_HOOK = "on_file_attachment_staged"
REBIND_HOOK = "on_session_canonical_rebind"
TEARDOWN_HOOK = "on_session_runtime_teardown"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path))


def _function_source(path: Path, name: str) -> str:
    src = _source(path)
    tree = ast.parse(src)

    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) and node.name == name:
            return ast.get_source_segment(src, node) or ""

    raise AssertionError(f"function not found: {path}:{name}")


def _decorated_method_source(path: Path, method_name: str) -> str:
    src = _source(path)
    tree = ast.parse(src)

    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            if not (
                isinstance(decorator.func, ast.Name)
                and decorator.func.id == "method"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and decorator.args[0].value == method_name
            ):
                continue

            return ast.get_source_segment(src, node) or ""

    raise AssertionError(f"RPC method not found: {method_name}")


def _valid_hooks() -> set[str]:
    tree = _tree(PLUGINS)

    for node in tree.body:
        target = None
        value = None

        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value

        if not (
            isinstance(target, ast.Name)
            and target.id == "VALID_HOOKS"
        ):
            continue

        assert isinstance(value, (ast.Set, ast.List, ast.Tuple))

        return {
            element.value
            for element in value.elts
            if isinstance(element, ast.Constant)
            and isinstance(element.value, str)
        }

    raise AssertionError("VALID_HOOKS assignment not found")


def test_generic_attachment_lifecycle_hooks_are_declared():
    hooks = _valid_hooks()

    assert ATTACH_HOOK in hooks
    assert REBIND_HOOK in hooks
    assert TEARDOWN_HOOK in hooks


def test_file_attach_emits_generic_trusted_staging_event():
    src = _decorated_method_source(
        METHODS_PROMPT,
        "file.attach",
    )

    assert ATTACH_HOOK in src

    for field in (
        "runtime_session_id",
        "canonical_session_id",
        "profile_home",
        "stored_path",
        "uploaded",
        "ref_path",
        "ref_text",
    ):
        assert field in src

    # Existing model-facing contract must remain intact.
    assert '"ref_path"' in src
    assert '"ref_text"' in src
    assert '"uploaded"' in src

    # Core must remain generic.
    lowered = src.lower()
    assert "delta_sandbox" not in lowered
    assert "att_" not in src


def test_session_identity_and_runtime_teardown_emit_generic_events():
    rebind_src = _function_source(
        SERVER,
        "_sync_session_key_after_compress",
    )

    assert REBIND_HOOK in rebind_src

    for field in (
        "runtime_session_id",
        "old_canonical_session_id",
        "new_canonical_session_id",
    ):
        assert field in rebind_src

    notify_src = _function_source(
        SERVER,
        "_notify_runtime_session_teardown",
    )

    assert TEARDOWN_HOOK in notify_src

    for field in (
        "runtime_session_id",
        "canonical_session_id",
        "reason",
    ):
        assert field in notify_src

    teardown_src = _function_source(
        SERVER,
        "_teardown_session",
    )

    assert "_notify_runtime_session_teardown" in teardown_src

    lowered = (
        rebind_src
        + notify_src
        + teardown_src
    ).lower()

    assert "delta_sandbox" not in lowered
    assert "att_" not in (
        rebind_src
        + notify_src
        + teardown_src
    )


def test_deferred_hydration_failure_converges_through_runtime_teardown():
    src = _function_source(
        SERVER,
        "_schedule_resume_hydration",
    )

    # The dangerous raw registry bypass discovered in P6 must disappear.
    assert "_sessions.pop(sid, None)" not in src

    # Claim must be identity-safe: a stale hydration worker may only
    # detach the exact runtime record it originally observed.
    assert "_pop_session_by_id" in src
    assert "expected_session=session" in src

    # Hydration failure must invalidate runtime-scoped plugin state through
    # the same generic notification used by normal teardown, without forcing
    # durable-session finalization that this path did not previously perform.
    assert "_notify_runtime_session_teardown" in src

    # Preserve the existing failed-resume lease-release behavior.
    assert "lease.release()" in src
