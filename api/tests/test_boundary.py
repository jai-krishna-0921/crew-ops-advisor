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


def test_nothing_writes_to_the_dataset() -> None:
    """The provided dataset is read only, everywhere, always.

    Regenerating or mutating it would silently move the answer keys that every
    golden test asserts against.
    """
    suspicious: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            if name not in {"open", "write_text", "write_bytes", "unlink", "rmtree"}:
                continue
            # A write mode on any call inside a module that also mentions the
            # dataset path is worth a human look.
            if "crew-ops-advisor-dataset" in source and name != "open":
                suspicious.append(f"{path.relative_to(SRC.parent.parent)}: {name}()")
            elif name == "open":
                for kw in node.keywords:
                    if (
                        kw.arg == "mode"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                        and any(m in kw.value.value for m in ("w", "a", "+"))
                        and "crew-ops-advisor-dataset" in source
                    ):
                        suspicious.append(
                            f"{path.relative_to(SRC.parent.parent)}: open(mode={kw.value.value!r})"
                        )

    assert not suspicious, (
        "These modules reference the dataset path and perform a write. The "
        "dataset is read only:\n  " + "\n  ".join(suspicious)
    )
