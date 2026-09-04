"""The boundary test.

The submission's central claim is that the language model plans and explains
but never produces a fact and never does arithmetic. A claim that is only
enforced by a prompt is not enforced at all, so this test enforces it
structurally: it walks the import graph of the deterministic core and fails if
any model client can be reached from it.

If this test fails, the fix is to move the offending code into `crewops.agent`.
The fix is never to add a package to the allowlist.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "crewops"

#: Packages that compute what a controller acts on. No model client may be
#: reachable from any of these, at any depth.
DETERMINISTIC_CORE: tuple[str, ...] = (
    "contracts",
    "domain",
    "rules",
    "ops",
    "store",
    "tools",
    "verify",
)

#: Anything that talks to a language model.
MODEL_CLIENTS: frozenset[str] = frozenset(
    {
        "anthropic",
        "langchain_anthropic",
        "langchain_openai",
        "langchain_core",
        "langgraph",
        "openai",
        "google.generativeai",
        "google.genai",
        "cohere",
        "mistralai",
        "ollama",
        "transformers",
        "litellm",
    }
)


def _python_files(package: str) -> list[Path]:
    root = SRC / package
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    """Every module name imported by a file, at any nesting depth."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _violates(module: str) -> bool:
    """True when `module` is, or lives inside, a model client package."""
    parts = module.split(".")
    return any(".".join(parts[: i + 1]) in MODEL_CLIENTS for i in range(len(parts)))


@pytest.mark.parametrize("package", DETERMINISTIC_CORE)
def test_core_package_imports_no_model_client(package: str) -> None:
    """No file in the deterministic core may import a model client."""
    offences: list[str] = []
    for path in _python_files(package):
        for module in sorted(_imported_modules(path)):
            if _violates(module):
                rel = path.relative_to(SRC.parent.parent)
                offences.append(f"{rel} imports {module}")

    assert not offences, (
        f"The deterministic core must not reach a language model. "
        f"crewops.{package} violates the boundary:\n  "
        + "\n  ".join(offences)
        + "\n\nMove this code into crewops.agent instead. Do not widen the allowlist."
    )


@pytest.mark.parametrize("package", DETERMINISTIC_CORE)
def test_core_package_imports_cleanly_without_model_libraries(package: str) -> None:
    """Importing the core must not pull a model client into `sys.modules`.

    This catches an indirect route the AST walk cannot see, for example a core
    module importing a sibling that itself imports a client.
    """
    root = SRC / package
    if not root.exists():
        pytest.skip(f"crewops.{package} not implemented yet")

    for stale in [m for m in sys.modules if m.startswith("crewops")]:
        del sys.modules[stale]
    before = set(sys.modules)

    __import__(f"crewops.{package}")

    pulled_in = {
        module for module in set(sys.modules) - before if _violates(module)
    }
    assert not pulled_in, (
        f"Importing crewops.{package} transitively loaded a model client: "
        f"{sorted(pulled_in)}. Something in the core imports the agent."
    )


def test_the_agent_is_where_the_model_lives() -> None:
    """The mirror of the rule above.

    A submission that claims a deliberate boundary should actually have a model
    on the other side of it. If nothing in `crewops.agent` imports a client,
    then either the agent is not built yet or the boundary is decorative.
    """
    agent_files = _python_files("agent")
    if not agent_files:
        pytest.skip("crewops.agent not implemented yet")

    uses_a_model = any(
        _violates(module) for path in agent_files for module in _imported_modules(path)
    )
    assert uses_a_model, (
        "crewops.agent imports no model client. The boundary only means "
        "something if the model is genuinely on the other side of it."
    )


#: Path fragments that identify the provided, read-only dataset.
DATASET_MARKERS: tuple[str, ...] = ("crew-ops-advisor-dataset", "DATASET_DIR", "DATA_DIR")

#: Calls that put bytes on disk or take them off it.
WRITE_CALLS: frozenset[str] = frozenset(
    {"write_text", "write_bytes", "unlink", "rmtree", "mkdir", "touch", "rename", "replace"}
)


def _writes_to_dataset(node: ast.Call) -> bool:
    """True when this specific call's target looks like the provided dataset.

    Inspecting the call's own receiver and arguments matters: a module that
    reads the dataset and separately writes a report elsewhere is fine, and an
    earlier version of this test wrongly failed exactly that case.
    """
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")

    if name == "open":
        mode = next(
            (
                kw.value.value
                for kw in node.keywords
                if kw.arg == "mode"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ),
            None,
        )
        if mode is None and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        if not isinstance(mode, str) or not any(m in mode for m in ("w", "a", "x", "+")):
            return False
        targets = [ast.unparse(a) for a in node.args[:1]]
    elif name in WRITE_CALLS:
        receiver = ast.unparse(func.value) if isinstance(func, ast.Attribute) else ""
        targets = [receiver, *(ast.unparse(a) for a in node.args)]
    else:
        return False

    return any(marker in target for target in targets for marker in DATASET_MARKERS)


def test_nothing_writes_to_the_dataset() -> None:
    """The provided dataset is read only, everywhere, always.

    Regenerating or mutating it would silently move the answer keys that every
    golden test asserts against, and every figure quoted in the README and the
    deck comes from the shipped pack.
    """
    offences: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _writes_to_dataset(node):
                offences.append(f"{path.relative_to(SRC.parent.parent)}: {ast.unparse(node)[:90]}")

    assert not offences, (
        "These calls write to the provided dataset, which is read only:\n  " + "\n  ".join(offences)
    )


def test_the_dataset_on_disk_is_unmodified() -> None:
    """A live check, not a static one.

    The static walk above can be defeated by a dynamically built path. This
    asserts the actual files are still there and still parse, so a test run
    that corrupted them fails loudly rather than silently rewriting the answer
    keys the golden suite compares against.
    """
    data_dir = SRC.parents[2] / "data" / "crew-ops-advisor-dataset" / "data"
    if not data_dir.exists():
        pytest.skip("dataset not present")

    expected = {
        "certifications.json",
        "costs.json",
        "crew.json",
        "duty_clocks.json",
        "flights.json",
        "questions.json",
        "reserve_pool.json",
        "risk_signals.json",
        "rosters.json",
        "rules.json",
        "scenarios.json",
    }
    present = {p.name for p in data_dir.glob("*.json")}
    assert expected <= present, f"Dataset files are missing: {sorted(expected - present)}"

    for name in sorted(expected):
        raw = (data_dir / name).read_text(encoding="utf-8")
        json.loads(raw)  # a truncated or rewritten file fails here


# ---------------------------------------------------------------------------
# Contract conformance.
#
# `contracts/tools.py` is the seam three workstreams build against. When the
# protocol widened and the registry did not follow, the flagship scenario
# silently started abstaining: a question names a person, the tool wanted a
# pairing, and nothing bridged the two. Nothing failed, it just stopped
# answering. These tests turn that class of drift into a build failure.


def _tool_surface() -> Any:
    from crewops.contracts.tools import ToolSurface

    return ToolSurface


def _protocol_methods() -> dict[str, Any]:
    import inspect

    return {
        name: fn
        for name, fn in inspect.getmembers(_tool_surface(), inspect.isfunction)
        if not name.startswith("_")
    }


def test_tool_names_match_the_protocol() -> None:
    """`TOOL_NAMES` is what the agent binds. It must be the protocol, exactly."""
    from crewops.contracts.tools import TOOL_NAMES

    assert set(TOOL_NAMES) == set(_protocol_methods()), (
        "TOOL_NAMES and the ToolSurface protocol have diverged.\n"
        f"  only in TOOL_NAMES: {sorted(set(TOOL_NAMES) - set(_protocol_methods()))}\n"
        f"  only in protocol:   {sorted(set(_protocol_methods()) - set(TOOL_NAMES))}"
    )


def test_retrieval_only_and_required_for_name_real_tools() -> None:
    """The graph's guards reference tools by name. A typo would disable a guard."""
    from crewops.contracts.tools import REQUIRED_FOR, RETRIEVAL_ONLY, TOOL_NAMES

    names = set(TOOL_NAMES)
    assert names.issuperset(RETRIEVAL_ONLY), (
        f"RETRIEVAL_ONLY names unknown tools: {sorted(RETRIEVAL_ONLY - names)}"
    )
    for claim, required in REQUIRED_FOR.items():
        assert names.issuperset(required), (
            f"{claim} names unknown tools: {sorted(required - names)}"
        )


def test_the_registry_implements_the_whole_tool_surface() -> None:
    """Every protocol method exists on the concrete registry."""
    try:
        from crewops.tools.registry import Tools
    except ImportError:
        pytest.skip("crewops.tools.registry not implemented yet")

    missing = sorted(name for name in _protocol_methods() if not hasattr(Tools, name))
    assert not missing, (
        f"crewops.tools.registry.Tools is missing {missing}. The agent binds every "
        "name in TOOL_NAMES, so a missing method is a question the system can never answer."
    )


def test_registry_signatures_have_not_fallen_behind_the_contract() -> None:
    """Every keyword the contract promises must exist on the implementation.

    The implementation may accept extra keywords. It may not drop one the
    protocol declares, because the agent and the offline resolver both call
    through the contract and a dropped keyword becomes a runtime abstention
    rather than a build failure.
    """
    import inspect

    try:
        from crewops.tools.registry import Tools
    except ImportError:
        pytest.skip("crewops.tools.registry not implemented yet")

    problems: list[str] = []
    for name, spec in _protocol_methods().items():
        impl = getattr(Tools, name, None)
        if impl is None:
            continue  # reported by the test above
        promised = {
            p
            for p, param in inspect.signature(spec).parameters.items()
            if param.kind is inspect.Parameter.KEYWORD_ONLY
        }
        actual = set(inspect.signature(impl).parameters)
        dropped = sorted(promised - actual)
        if dropped:
            problems.append(f"{name} is missing {dropped}")

    assert not problems, (
        "These tools accept fewer arguments than contracts/tools.py promises:\n  "
        + "\n  ".join(problems)
        + "\n\nWiden the implementation to match the contract, or change the "
        "contract deliberately and tell the other workstreams."
    )


def test_agent_tool_schemas_match_the_contract() -> None:
    """The agent's argument models must expose what the contract promises.

    This is the same drift as the registry test above, one layer further out,
    and it is the more dangerous of the two. Pydantic drops unknown fields
    silently, so an argument missing from a ToolSpec's model is not an error:
    the model asks for it, the value evaporates, and the tool reports that it
    was never given one. It cost the flagship scenario twice before this test
    existed.
    """
    import inspect

    try:
        from crewops.agent.toolspecs import TOOL_SPECS
    except ImportError:
        pytest.skip("crewops.agent.toolspecs not implemented yet")

    protocol = _protocol_methods()
    problems: list[str] = []
    for spec in TOOL_SPECS:
        promised = {
            name
            for name, param in inspect.signature(protocol[spec.name]).parameters.items()
            if param.kind is inspect.Parameter.KEYWORD_ONLY
        }
        exposed = set(spec.args_model.model_fields)
        dropped = sorted(promised - exposed)
        if dropped:
            problems.append(f"{spec.name} cannot accept {dropped}")

    assert not problems, (
        "These agent tool schemas accept fewer arguments than the contract "
        "promises:\n  "
        + "\n  ".join(problems)
        + "\n\nPydantic drops unknown fields without complaining, so the "
        "argument is not rejected, it is silently lost."
    )
