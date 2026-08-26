#!/usr/bin/env python3
"""
Scenario tests for the base_class / include_dirs targeting modes.

    python test/run_tests.py

Each scenario runs a real rule against the fixture trees, asserts exactly
which functions were touched, then restores the fixtures. The expected sets
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
REMOVED_PREFIX = "   ✨ Removed: "
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
INJECT_ALL_SRC = {
    "directory": "test/src",
    "function": ""
}

INJECT_ALL_PROJ = {
    "directory": "test/proj/src",
    "function": ""
}

#
# Every function defined under test/src, i.e. what INJECT_ALL_SRC produces.
#
ALL_SRC_FUNCTIONS = {
    "NetworkMgr::Connect",
    "NetworkMgr::Disconnect",
    "NetworkMgr::Run",
    "OrderMgr::OnData",
    "OrderMgr::OnConnected",
    "OrderMgr::SubmitOrder",
    "MarketData::OnSnapshot",
    "MarketData::OnTick",
    "IStrategy::Stop",
    "StrategyEngine::Run",
    "StrategyEngine::Stop",
    "AlphaStrategy::Run",
    "AlphaStrategy::Evaluate",
    "AlphaStrategy::Rebalance",
    "Normalize",
    "util::Reset"
}

ALL_RUNS = {
    "NetworkMgr::Run",
    "StrategyEngine::Run",
    "AlphaStrategy::Run"
}

EXECUTOR_OVERRIDES = {
    "OrderExecutor::Execute",
    "SlowExecutor::Execute",
    "FastExecutor::Execute"
}

SCENARIOS = [
    {
        "name": "same tree, relative includes, no include_dirs",
        "rule": {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": "Run"
        },
        "injected": {
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        }
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
        "injected": EXECUTOR_OVERRIDES
    },
    {
        "name": "separate include root, include_dirs MISSING -> warn, no writes",
        "rule": {
            "directory": "test/proj/src",
            "base_class": "IExecutor",
            "function": "Execute"
        },
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
        "injected": {
            "IStrategy::Stop",
            "StrategyEngine::Stop"
        }
    },
    {
        "name": "no base_class: labels are qualified all the same",
        "rule": {
            "directory": "test/src",
            "function": "Run"
        },
        "injected": ALL_RUNS
    },
    {
        "name": "free functions: namespace qualified, bare at file scope",
        "rule": {
            "directory": "test/src/util",
            "function": ""
        },
        "injected": {
            "util::Reset",
            "Normalize"
        }
    },
    {
        "name": "empty function: every method in the hierarchy",
        "rule": {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": ""
        },
        "injected": {
            "IStrategy::Stop",
            "StrategyEngine::Run",
            "StrategyEngine::Stop",
            "AlphaStrategy::Run",
            "AlphaStrategy::Evaluate",
            "AlphaStrategy::Rebalance"
        }
    },
    #
    # remove side: the same rule fields must take traces back out again.
    #
    {
        "name": "remove: unfiltered rule strips the whole file",
        "setup": INJECT_ALL_SRC,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": ""
        },
        "removed": set(),
        "removed_count": len(ALL_SRC_FUNCTIONS),
        "remaining": 0
    },
    {
        "name": "remove: by function name only",
        "setup": INJECT_ALL_SRC,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": "Run"
        },
        "removed": ALL_RUNS,
        "remaining": len(ALL_SRC_FUNCTIONS) - len(ALL_RUNS)
    },
    {
        "name": "remove: by base_class, LocalCache::Execute survives",
        "setup": INJECT_ALL_PROJ,
        "setup_include_dirs": [
            "test/proj/include"
        ],
        "mode": "remove",
        "rule": {
            "directory": "test/proj/src",
            "base_class": "IExecutor",
            "function": "Execute"
        },
        "include_dirs": [
            "test/proj/include"
        ],
        "removed": EXECUTOR_OVERRIDES,
        "remaining": 1
    },
    {
        "name": "remove: base_class with include_dirs MISSING -> warn, no writes",
        "setup": INJECT_ALL_PROJ,
        "setup_include_dirs": [
            "test/proj/include"
        ],
        "mode": "remove",
        "rule": {
            "directory": "test/proj/src",
            "base_class": "IExecutor",
            "function": "Execute"
        },
        "removed": set(),
        "warns": True,
        "remaining": 4
    },
    {
        "name": "remove: function-level exclude keeps every Run",
        "setup": INJECT_ALL_SRC,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": ""
        },
        "exclude": [
            {
                "directory": "test/src",
                "function": "Run"
            }
        ],
        "removed": ALL_SRC_FUNCTIONS - ALL_RUNS,
        "remaining": len(ALL_RUNS)
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


def fresh_stats():

    return {
        "files_scanned": 0,
        "files_modified": 0,
        "files_excluded": 0,
        "trace_injected": 0,
        "trace_removed": 0
    }


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


def count_traces():

    total = 0

    for path in HERE.rglob("*.cpp"):
        total += path.read_text(
            encoding="utf-8"
        ).count("ScopeTrace trace(")

    return total


def labels_with_prefix(logger, prefix):

    return {
        line[len(prefix):].removesuffix("()")
        for line in logger.lines
        if line.startswith(prefix)
    }


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


def run_scenario(scenario):
    """Returns a list of failure descriptions (empty means the test passed)."""

    if scenario.get("setup"):

        process_rule(
            scenario["setup"],
            "inject",
            [],
            CaptureLogger(),
            fresh_stats(),
            include_dirs=scenario.get("setup_include_dirs", [])
        )

    logger = CaptureLogger()
    stats = fresh_stats()

    process_rule(
        scenario["rule"],
        scenario.get("mode", "inject"),
        scenario.get("exclude", []),
        logger,
        stats,
        include_dirs=scenario.get("include_dirs", [])
    )

    failures = []

    checks = [
        ("injected", INJECTED_PREFIX, "trace_injected"),
        ("removed", REMOVED_PREFIX, "trace_removed")
    ]

    for key, prefix, stat_key in checks:

        if key not in scenario:
            continue

        actual = labels_with_prefix(logger, prefix)
        expected = scenario[key]

        if actual != expected:

            failures.append(
                f"{key} mismatch\n"
                f"      missing: {sorted(expected - actual) or '-'}\n"
                f"      extra  : {sorted(actual - expected) or '-'}"
            )

        #
        # An explicit count covers the whole-file remove path, which deletes
        # traces without being able to name the function they sat in.
        #
        count_key = f"{key}_count"
        expected_count = scenario.get(count_key, len(expected))

        if stats[stat_key] != expected_count:

            failures.append(
                f"stats {stat_key}={stats[stat_key]}, "
                f"expected {expected_count}"
            )

    if "remaining" in scenario:

        remaining = count_traces()

        if remaining != scenario["remaining"]:

            failures.append(
                f"{remaining} traces left in the fixtures, "
                f"expected {scenario['remaining']}"
            )

    warned = INCOMPLETE_WARNING in logger.text
    expected_warning = scenario.get("warns", False)

    if warned != expected_warning:

        failures.append(
            f"expected warning={expected_warning}, got {warned}"
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
