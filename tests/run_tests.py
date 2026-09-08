#!/usr/bin/env python3
"""Dependency-free runner for this repository's simple assertion tests."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parent
failures: list[str] = []
passed = 0
for path in sorted(ROOT.glob("test_*.py")):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        try:
            function()
            passed += 1
        except Exception as exc:  # pragma: no cover - command-line reporting
            failures.append(f"{path.name}:{name}: {exc!r}")
if failures:
    raise SystemExit("\n".join(failures))
print(f"tests_passed={passed}")

