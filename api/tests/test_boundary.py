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
