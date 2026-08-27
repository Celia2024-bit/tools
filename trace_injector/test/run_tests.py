#!/usr/bin/env python3
"""
The regression check for trace_injector. Change anything, then run:

    python test/run_tests.py

Exit code 0 means nothing that used to work is broken. No arguments, no
environment setup, no network — it finds libclang itself and puts the
fixture trees back exactly as it found them.

Three parts, in order:

  1. SCENARIOS      - real rules against the fixture trees under test/,
                      asserting the exact set of functions touched. The
                      expected sets are exact, so a class that must NOT
                      match (NetworkMgr::Run, LocalCache::Execute) is
                      asserted by its absence.

  2. SELF_CHECKS    - breaks the tool on purpose and confirms part 1
                      notices. A green suite only means something if it
                      can go red; these guard against an assertion
                      quietly becoming vacuous.

  3. fixture audit  - the fixtures must be trace-free before and after,
                      byte for byte. Otherwise part 1 was measuring
                      leftovers from the previous run.

Adding a scenario: append to SCENARIOS. Keys are documented above the
list. If your change makes an existing scenario fail, that is the point
of this file — read the diff it prints before editing the expectation.

If libclang cannot be found automatically, point at it:

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


#
# ---------------------------------------------------------------- libclang
#
# The clang python bindings load libclang through the OS loader, which does
# not look inside site-packages. Finding it here rather than making every
# caller export a variable is the difference between "run this file" and
# "run this file after reading the README".
#
def libclang_candidates():

    import clang

    names = {
        "win32": "libclang.dll",
        "darwin": "libclang.dylib"
    }

    name = names.get(sys.platform, "libclang.so")

    yield Path(clang.__file__).parent / "native" / name

    for base in (
        Path(sys.prefix),
        Path(sys.prefix) / "Library",
        Path("C:/Program Files/LLVM"),
        Path("/usr/lib/llvm-14"),
        Path("/usr/lib"),
        Path("/usr/local/lib"),
        Path("/opt/homebrew/lib")
    ):
        yield base / "bin" / name
        yield base / "lib" / name
        yield base / name


def configure_libclang():
    """Returns the path in use, or None if the default loader already works."""

    from clang import cindex

    explicit = os.environ.get(
        "TRACE_INJECTOR_LIBCLANG",
        ""
    )

    if explicit:
        cindex.Config.set_library_file(explicit)
        return explicit

    try:
        cindex.Index.create()
        return None
    except cindex.LibclangError:
        pass

    for candidate in libclang_candidates():

        if not candidate.is_file():
            continue

        cindex.Config.set_library_file(str(candidate))

        try:
            cindex.Index.create()
            return str(candidate)
        except cindex.LibclangError:
            cindex.Config.loaded = False

    raise SystemExit(
        "Could not load libclang. Install it (pip install libclang) or "
        "set TRACE_INJECTOR_LIBCLANG to the shared library."
    )


LIBCLANG_IN_USE = configure_libclang()

from trace_injector_pkg import targets
from trace_injector_pkg.config import load_config, resolve_mode_and_rules
from trace_injector_pkg.processor import process_rule

INJECTED_PREFIX = "   ✨ Injected: "
REMOVED_PREFIX = "   ✨ Removed: "
INCOMPLETE_WARNING = "Base-class matching may be incomplete"
TRACE_MARKER = "ScopeTrace trace("

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

#
# Scenario keys, all optional except name and one of rule/config:
#
#   name                 what prints in the report
#   rule                 the rule dict under test
#   config               run a shipped config file instead of `rule`
#   mode                 "inject" (default) or "remove"
#   exclude              exclude entries passed alongside `rule`
#   include_dirs         clang -I paths for the rule under test
#   setup                a rule injected first, to give remove something to do
#   setup_config         same, but from a shipped config file
#   setup_include_dirs   clang -I paths for `setup`
#   injected / removed   the EXACT set of qualified names expected in the log
#   injected_count /
#   removed_count        override the stat check, for paths that cannot name
#                        the function they touched
#   remaining            traces left in the fixtures afterwards
#   warns                whether the incomplete-match warning must appear
#
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
    # A definition living in a header must never be placed by its header line
    # number into the .cpp. test/inline_hdr is built so that going wrong is
    # visible: Widget::Run sits on line 11 of Widget.h, and line 11 of
    # Widget.cpp is an opening brace inside Widget::Later.
    #
    {
        "name": "header-inline definition is not injected into the .cpp",
        "rule": {
            "directory": "test/inline_hdr",
            "function": "Run"
        },
        "injected": set(),
        "remaining": 0
    },
    {
        "name": "the .cpp definition in that same tree still gets injected",
        "rule": {
            "directory": "test/inline_hdr",
            "function": ""
        },
        "injected": {
            "Widget::Later"
        },
        "remaining": 1
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
    #
    # Runs the shipped examples for real, not just through validation: the
    # remove example claims to be the exact undo of the inject one, and
    # "remaining: 0" is the only thing that actually proves it.
    #
    {
        "name": "examples: base_class inject then remove leaves nothing",
        "setup_config": "config_base_class_includedirs_example.json",
        "config": "config_base_class_remove_example.json",
        "removed": EXECUTOR_OVERRIDES,
        "remaining": 0
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


def fixture_files():
    return sorted(
        HERE.rglob("*.cpp")
    )


def snapshot_fixtures():

    saved = {}

    for path in fixture_files():
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

    for path in fixture_files():
        total += path.read_text(
            encoding="utf-8"
        ).count(TRACE_MARKER)

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


def check_fixtures_clean(saved=None):
    """
    The fixtures carry no traces at rest. Before the run that means the
    previous run cleaned up after itself; after it, that this one did.
    `saved` also demands byte equality, catching debris a trace count misses.
    """

    failures = []

    for path in fixture_files():

        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()

        if TRACE_MARKER in text:
            failures.append(
                f"{name}: {text.count(TRACE_MARKER)} leftover trace(s)"
            )

        if saved is not None and text != saved.get(path, text):
            failures.append(
                f"{name}: content differs from the snapshot"
            )

    return failures


def apply_config(config_file, logger, stats):
    """Run every rule in a shipped config file, the way the CLI does."""

    mode, rules, exclude_rules, include_dirs = resolve_mode_and_rules(
        load_config(ROOT / config_file)
    )

    for rule in rules:

        process_rule(
            rule,
            mode,
            exclude_rules,
            logger,
            stats,
            include_dirs=include_dirs
        )


def run_scenario(scenario):
    """Returns a list of failure descriptions (empty means the test passed)."""

    if scenario.get("setup_config"):

        apply_config(
            scenario["setup_config"],
            CaptureLogger(),
            fresh_stats()
        )

    elif scenario.get("setup"):

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

    if scenario.get("config"):

        apply_config(
            scenario["config"],
            logger,
            stats
        )

    else:

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


def run_all_scenarios(saved, report=None):
    """
    Runs every scenario, restoring the fixtures around each one. Returns the
    set of names that failed. `report` receives (name, failures) per scenario
    when the caller wants the detail printed.
    """

    failed = set()

    for scenario in SCENARIOS:

        try:
            failures = run_scenario(scenario)
        except Exception as error:
            failures = [f"raised {type(error).__name__}: {error}"]
        finally:
            restore_fixtures(saved)

        if failures:
            failed.add(scenario["name"])

        if report:
            report(scenario["name"], failures)

    return failed


#
# ------------------------------------------------------------- self checks
#
# Each entry breaks the tool one way and names the scenarios that must
# notice. `must_fail` is what makes the suite worth running; `must_pass`
# proves the breakage was targeted rather than burning the whole thing down.
#
# Only the listed names are judged, so adding a scenario never invalidates a
# self check.
#
def patch_remove_ignores_filters():
    """Make every remove take the coarse whole-file path."""

    from trace_injector_pkg import processor

    original = processor.remove_trace_from_file

    def coarse(cpp_file, logger, stats, **ignored):
        return original(cpp_file, logger, stats)

    processor.remove_trace_from_file = coarse

    def undo():
        processor.remove_trace_from_file = original

    return undo


def patch_accept_any_file():
    """Stop restricting definitions to the file being rewritten."""

    original = targets.in_main_file
    targets.in_main_file = lambda node, tu: True

    def undo():
        targets.in_main_file = original

    return undo


def patch_warning_threshold():
    """Report ordinary errors too, which fires on every already-injected file."""

    from clang import cindex

    original = targets.MIN_REPORTED_SEVERITY
    targets.MIN_REPORTED_SEVERITY = cindex.Diagnostic.Error

    def undo():
        targets.MIN_REPORTED_SEVERITY = original

    return undo


def patch_example_base_class():
    """Typo the base_class inside the shipped example configs."""

    original = globals()["load_config"]

    def broken(config_file):

        config = original(config_file)

        for rule in config.get("inject", []) + config.get("remove", []):
            if rule.get("base_class"):
                rule["base_class"] = "INotARealBaseClass"

        return config

    globals()["load_config"] = broken

    def undo():
        globals()["load_config"] = original

    return undo


SELF_CHECKS = [
    {
        "name": "targeted remove degraded to whole-file",
        "patch": patch_remove_ignores_filters,
        "must_fail": [
            "remove: by function name only",
            "remove: by base_class, LocalCache::Execute survives",
            "remove: base_class with include_dirs MISSING -> warn, no writes",
            "remove: function-level exclude keeps every Run",
            "examples: base_class inject then remove leaves nothing"
        ],
        "must_pass": [
            "remove: unfiltered rule strips the whole file"
        ]
    },
    {
        "name": "definitions no longer restricted to the main file",
        "patch": patch_accept_any_file,
        "must_fail": [
            "header-inline definition is not injected into the .cpp",
            "the .cpp definition in that same tree still gets injected"
        ],
        "must_pass": [
            "same tree, relative includes, no include_dirs",
            "free functions: namespace qualified, bare at file scope"
        ]
    },
    {
        "name": "parse warning widened past fatal",
        "patch": patch_warning_threshold,
        "must_fail": [
            "remove: by base_class, LocalCache::Execute survives",
            "examples: base_class inject then remove leaves nothing"
        ],
        "must_pass": [
            "separate include root, include_dirs given",
            "separate include root, include_dirs MISSING -> warn, no writes"
        ]
    },
    {
        "name": "example config base_class typo",
        "patch": patch_example_base_class,
        "must_fail": [
            "examples: base_class inject then remove leaves nothing"
        ],
        "must_pass": [
            "remove: by base_class, LocalCache::Execute survives"
        ]
    }
]


def run_self_check(self_check, saved):

    undo = self_check["patch"]()

    try:
        failed = run_all_scenarios(saved)
    finally:
        undo()

    problems = []

    for name in self_check["must_fail"]:

        if name not in failed:
            problems.append(
                f"not detected by: {name}"
            )

    for name in self_check["must_pass"]:

        if name in failed:
            problems.append(
                f"collateral damage to: {name}"
            )

    return problems


#
# ------------------------------------------------------------------ report
#
class Report:

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def record(self, name, failures):

        if failures:

            self.failed += 1
            print(f"FAIL  {name}")

            for failure in failures:
                print(f"      {failure}")

        else:

            self.passed += 1
            print(f"pass  {name}")


def main():

    os.chdir(ROOT)

    if LIBCLANG_IN_USE:
        print(f"libclang: {LIBCLANG_IN_USE}")
        print()

    report = Report()

    print("-- scenarios")
    report.record(
        "fixtures start clean",
        check_fixtures_clean()
    )
    report.record(
        "example configs pass validation",
        check_example_configs()
    )

    saved = snapshot_fixtures()

    try:
        run_all_scenarios(saved, report=report.record)
    finally:
        restore_fixtures(saved)

    #
    # Skipped when the suite is already red: a self check asserts which
    # scenarios fail, so it can only be read against a green baseline.
    #
    print()

    if report.failed:

        print(
            f"-- self checks skipped, {report.failed} scenario(s) already "
            "failing"
        )

    else:

        print("-- self checks (breaking the tool on purpose)")

        try:
            for self_check in SELF_CHECKS:
                report.record(
                    self_check["name"],
                    run_self_check(self_check, saved)
                )
        finally:
            restore_fixtures(saved)

        print()
        print("-- cleanup")
        report.record(
            "fixtures restored byte for byte",
            check_fixtures_clean(saved)
        )

    print()
    print(f"{report.passed} passed, {report.failed} failed")

    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
