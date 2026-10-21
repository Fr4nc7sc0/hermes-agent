"""Contract for the Delta sandbox remote Hermes plugin manifest.

No YAML dependency is required for this RED contract.

The manifest must identify a flat bundled standalone plugin whose
effective Hermes plugin key is `delta_sandbox_remote`, and it must
declare exactly the generic attachment and session-start lifecycle hooks
used by the Delta adapter.
"""

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

MANIFEST = (
    REPO
    / "plugins"
    / "delta_sandbox_remote"
    / "plugin.yaml"
)

EXPECTED_NAME = "delta_sandbox_remote"

EXPECTED_HOOKS = (
    "on_file_attachment_staged",
    "on_session_start",
)


def red(reason: str) -> int:
    print(
        "RED_EXPECTED="
        + reason
    )

    return 1


def main() -> int:
    if not MANIFEST.is_file():
        return red(
            "DELTA_PLUGIN_MANIFEST_MISSING"
        )

    text = MANIFEST.read_text(
        encoding="utf-8-sig"
    )

    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
    ]

    required_exact = (
        "name: delta_sandbox_remote",
        "kind: standalone",
        "provides_hooks:",
        "  - on_file_attachment_staged",
        "  - on_session_start",
    )

    for required in required_exact:
        if required not in lines:
            return red(
                "MANIFEST_TERM_MISSING:"
                + required.strip()
            )

    name_lines = [
        line
        for line in lines
        if line.startswith("name:")
    ]

    if name_lines != [
        "name: delta_sandbox_remote"
    ]:
        raise AssertionError(
            "manifest must define exactly one "
            "canonical plugin name"
        )

    kind_lines = [
        line
        for line in lines
        if line.startswith("kind:")
    ]

    if kind_lines != [
        "kind: standalone"
    ]:
        raise AssertionError(
            "manifest must be standalone"
        )

    forbidden_prefixes = (
        "provides_tools:",
        "capabilities:",
        "requires_env:",
        "python_dependencies:",
        "requires_plugins:",
    )

    for prefix in forbidden_prefixes:
        if any(
            line.startswith(prefix)
            for line in lines
        ):
            raise AssertionError(
                "unexpected capability or dependency: "
                + prefix
            )

    hook_index = lines.index(
        "provides_hooks:"
    )

    hook_values = []

    for line in lines[
        hook_index + 1:
    ]:
        if (
            line
            and not line.startswith(" ")
        ):
            break

        stripped = line.strip()

        if stripped.startswith("- "):
            hook_values.append(
                stripped[2:]
            )

    if tuple(hook_values) != EXPECTED_HOOKS:
        raise AssertionError(
            "manifest hook declaration must "
            "contain exactly "
            + repr(EXPECTED_HOOKS)
        )

    # Flat plugin path + manifest name means
    # Hermes manifest_key resolves to this same id.
    plugin_id = EXPECTED_NAME

    print(
        "EXPECTED_PLUGIN_ID="
        + plugin_id
    )

    print(
        "EXPECTED_ENABLEMENT="
        "plugins.enabled:"
        + plugin_id
    )

    print(
        "PLUGIN_MANIFEST_CONTRACT=GREEN"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
