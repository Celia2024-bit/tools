#!/usr/bin/env python3
"""
Scenario tests for the base_class / include_dirs targeting modes.

    python test/run_tests.py

Each scenario runs a real rule against the fixture trees, asserts exactly
which functions got a trace, then restores the fixtures. The expected sets
are exact, so a class that must NOT match (NetworkMgr::Run, LocalCache::
Execute) is asserted by its absence.

If libclang.dll is not on the DLL search path, point at it explicitly:

    TRACE_INJECTOR_LIBCLANG=C:/Python/Lib/site-packages/clang/native/libclang.dll \
        python test/run_tests.py
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(
    encoding="utf-8",
    errors="replace"
)

_LIBCLANG = os.environ.get(
    "TRACE_INJECTOR_LIBCLANG",
    ""
)

if _LIBCLANG:

    from clang import cindex

    cindex.Config.set_library_file(_LIBCLANG)

from trace_injector_pkg.config import load_config, resolve_mode_and_rules
from trace_injector_pkg.processor import process_rule

INJECTED_PREFIX = "   ✨ Injected: "
INCOMPLETE_WARNING = "Base-class matching may be incomplete"

#
# Two fixture trees, on purpose:
#
#   test/src        - base class header sits next to the .cpp files and every
#                     #include is relative to its own source file, so clang
#                     resolves everything unaided => include_dirs not needed.
#
#   test/proj       - base class lives under a separate include root
#                     (test/proj/include) and OrderExecutor.h includes it as
#                     "framework/IExecutor.h" => include_dirs required.
#
SCENARIOS = [
    {
        "name": "same tree, relative includes, no include_dirs",
        "rule": {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": "Run"
        },
        "include_dirs": [],
        "injected": {
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        },
        "warns": False
    },
    {
        "name": "separate include root, include_dirs given",
        "rule": {
            "directory": "test/proj/src",
            "base_class": "IExecutor",
            "function": "Execute"
        },
        "include_dirs": [
            "test/proj/include"
        ],
        "injected": {
            "OrderExecutor::Execute",
            "FastExecutor::Execute",
            "SlowExecutor::Execute"
        },
        "warns": False
    },
    {
        "name": "separate include root, include_dirs MISSING -> warn, no writes",
        "rule": {
            "directory": "test/proj/src",
            "base_class": "IExecutor",
            "function": "Execute"
        },
        "include_dirs": [],
        "injected": set(),
        "warns": True
    },
    {
        "name": "is-a: the base class own implementation counts too",
        "rule": {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": "Stop"
        },
        "include_dirs": [],
        "injected": {
            "IStrategy::Stop",
            "StrategyEngine::Stop"
        },
        "warns": False
    },
    {
        "name": "no base_class: labels are qualified all the same",
        "rule": {
            "directory": "test/src",
            "function": "Run"
        },
        "include_dirs": [],
        "injected": {
            "NetworkMgr::Run",
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        },
        "warns": False
    },
    {
        "name": "free functions: namespace qualified, bare at file scope",
        "rule": {
            "directory": "test/src/util",
            "function": ""
        },
        "include_dirs": [],
        "injected": {
            "util::Reset",
            "Normalize"
        },
        "warns": False
    },
    {
        "name": "empty function: every method in the hierarchy",
        "rule": {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": ""
        },
        "include_dirs": [],
        "injected": {
            "IStrategy::Stop",
            "StrategyEngine::Run",
            "StrategyEngine::Stop",
            "AlphaStrategy::Run",
            "AlphaStrategy::Evaluate",
            "AlphaStrategy::Rebalance"
        },
        "warns": False
    }
]


class CaptureLogger:

    def __init__(self):
        self.lines = []

    def log(self, msg=""):
        self.lines.append(msg)

    @property
    def text(self):
        return "\n".join(self.lines)


def snapshot_fixtures():

    saved = {}

    for path in HERE.rglob("*.cpp"):
        saved[path] = path.read_text(
            encoding="utf-8"
        )

    return saved


def restore_fixtures(saved):

    for path, text in saved.items():

        if path.read_text(encoding="utf-8") != text:
            path.write_text(
                text,
                encoding="utf-8"
            )


def injected_labels(logger):

    return {
        line[len(INJECTED_PREFIX):].removesuffix("()")
        for line in logger.lines
        if line.startswith(INJECTED_PREFIX)
    }


def run_scenario(scenario):
    """Returns a list of failure descriptions (empty means the test passed)."""

    logger = CaptureLogger()

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "files_excluded": 0,
        "trace_injected": 0,
        "trace_removed": 0
    }

    process_rule(
        scenario["rule"],
        "inject",
        [],
        logger,
        stats,
        include_dirs=scenario["include_dirs"]
    )

    failures = []

    actual = injected_labels(logger)
    expected = scenario["injected"]

    if actual != expected:

        failures.append(
            f"injected mismatch\n"
            f"      missing: {sorted(expected - actual) or '-'}\n"
            f"      extra  : {sorted(actual - expected) or '-'}"
        )

    warned = INCOMPLETE_WARNING in logger.text

    if warned != scenario["warns"]:

        failures.append(
            f"expected warning={scenario['warns']}, got {warned}"
        )

    if stats["trace_injected"] != len(expected):

        failures.append(
            f"stats trace_injected={stats['trace_injected']}, "
            f"expected {len(expected)}"
        )

    return failures


def check_example_configs():
    """
    Every shipped example must survive config validation. Guards against the
    validation rules and the examples drifting apart — a rejected example is
    a crash the first time someone copies it.
    """

    failures = []

    for config_file in sorted(
        ROOT.glob("config_*example*.json")
    ):

        try:
            resolve_mode_and_rules(
                load_config(config_file)
            )
        except Exception as error:
            failures.append(
                f"{config_file.name}: {error}"
            )

    return failures


def main():

    os.chdir(ROOT)

    saved = snapshot_fixtures()

    passed = 0
    failed = 0

    example_failures = check_example_configs()

    if example_failures:

        failed += 1
        print("FAIL  example configs pass validation")

        for failure in example_failures:
            print(f"      {failure}")

    else:

        passed += 1
        print("pass  example configs pass validation")

    try:

        for scenario in SCENARIOS:

            try:
                failures = run_scenario(scenario)
            finally:
                restore_fixtures(saved)

            if failures:

                failed += 1
                print(f"FAIL  {scenario['name']}")

                for failure in failures:
                    print(f"      {failure}")

            else:

                passed += 1
                print(f"pass  {scenario['name']}")

    finally:

        restore_fixtures(saved)

    print()
    print(f"{passed} passed, {failed} failed")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
