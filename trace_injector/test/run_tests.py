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

                      Every scenario also gets check_include_consistency()
                      for free: whatever it was written to measure, the
                      state it leaves behind still has to be one the
                      compiler would accept.

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

import contextlib
import io
import json
import os
import re
import shutil
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
# The tool's own locator, not a copy of it. Most checks here call process_rule
# directly and never reach cli.py, so without this the suite would need its own
# way of finding libclang — and then it would be testing the tool while relying
# on a search path the tool does not use.
#
from trace_injector_pkg.libclang import configure as configure_libclang

LIBCLANG_IN_USE = configure_libclang()

from trace_injector_pkg import targets
from trace_injector_pkg.cli import cleanup_logs, main as cli_main
from trace_injector_pkg.config import (
    load_config,
    resolve_mode_and_rules
)
from trace_injector_pkg.processor import process_rule

INJECTED_PREFIX = "   ✨ Injected: "
REMOVED_PREFIX = "   ✨ Removed: "
INCOMPLETE_WARNING = "Base-class matching may be incomplete"
TRACE_MARKER = "ScopeTrace trace("

EXAMPLES_DIR = "configs_examples"

#
# Spelled out here rather than imported from the package on purpose. The
# leftover checks are meant to be an independent opinion about what the
# injector writes; importing the tool's own marker list would make them agree
# with the bug instead of catching it.
#
INJECTED_MARKERS = (
    TRACE_MARKER,
    "static const char* __param_names[]",
    "validate_params("
)

#
# The include each kind needs, spelled out for the same reason: the exact line
# the injector must write, and the injected code that is proof it was needed.
#
# One include per file that has such code, none in a file that has not. The two
# ways to get this wrong are opposites and neither is loud: a missing include is
# a file that does not compile, and a leftover one is a file that pulls in
# Types.h for nothing — or, worse, keeps compiling until somebody deletes the
# header it names.
#
INJECTED_INCLUDES = {
    '#include "ScopeTrace.h"  // inject automatically: include for trace':
        (TRACE_MARKER,),
    '#include "ParameterCheck.h"  // inject automatically: include for validate':
        ("validate_params(",)
}

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
# Same sweep, but asking for both kinds. Only the functions that take
# parameters get a validate block, which is what makes it a real test of
# kind-blind removal: most functions carry one block, a few carry two.
#
INJECT_ALL_SRC_VALIDATE = {
    "directory": "test/src",
    "function": "",
    "inject_type": [
        "trace",
        "validate"
    ]
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
    "util::Reset",
    "RiskChecker::CheckOrder",
    "RiskChecker::CheckLimits",
    "RiskChecker::Margin",
    "RiskChecker::Snapshot",
    "RiskChecker::ResetCounters"
}

ALL_RUNS = {
    "NetworkMgr::Run",
    "StrategyEngine::Run",
    "AlphaStrategy::Run"
}

#
# The functions under test/src that take parameters, i.e. the only ones a
# "validate" inject writes a second block into. RiskChecker::Snapshot qualifies
# on two of its three parameters — the third has no name.
#
VALIDATED_SRC_FUNCTIONS = {
    "OrderMgr::OnData",
    "OrderMgr::SubmitOrder",
    "Normalize",
    "RiskChecker::CheckOrder",
    "RiskChecker::CheckLimits",
    "RiskChecker::Margin",
    "RiskChecker::Snapshot"
}

#
# The same two things counted in blocks rather than in names, because the two
# numbers genuinely differ: RiskChecker::Margin is overloaded, so two separate
# definitions share one qualified name. A set of log labels collapses them; the
# stats counter and the file contents do not.
#
SRC_OVERLOAD_EXTRAS = 1                 # the second RiskChecker::Margin

SRC_TRACE_BLOCKS = len(ALL_SRC_FUNCTIONS) + SRC_OVERLOAD_EXTRAS
SRC_VALIDATE_BLOCKS = len(VALIDATED_SRC_FUNCTIONS) + SRC_OVERLOAD_EXTRAS

#
# One marker per trace block, two per validate block (the name table and the
# call). What INJECT_ALL_SRC_VALIDATE leaves behind, in marker occurrences.
#
ALL_SRC_MARKERS_WITH_VALIDATE = (
    SRC_TRACE_BLOCKS
    +
    2 * SRC_VALIDATE_BLOCKS
)

EXECUTOR_OVERRIDES = {
    "OrderExecutor::Execute",
    "SlowExecutor::Execute",
    "FastExecutor::Execute"
}

#
# Every function defined under test/proj. LocalCache::Execute has the method
# name but no base class, which is what makes it useful in the base_class
# scenarios and why it has to be added back for an unfiltered sweep.
#
ALL_PROJ_FUNCTIONS = EXECUTOR_OVERRIDES | {
    "LocalCache::Execute"
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
#   setup_injected       injected markers the setup must have planted, checked
#                        before the rule under test runs — a remove scenario
#                        asserting "nothing left" passes just as well when the
#                        setup put nothing there
#   injected / removed   the EXACT set of qualified names expected in the log
#   injected_count /
#   removed_count        override the stat check, for paths that cannot name
#                        the function they touched
#   remaining            traces left in the fixtures afterwards
#   remaining_injected   injected marker occurrences of ANY kind left behind,
#                        which is what catches validate debris a trace count
#                        walks straight past
#   validate_blocks      how many validate blocks must be in the fixtures, each
#                        of them read back and checked name-by-name against the
#                        arguments it passes — see check_validate_blocks
#   round_trip           {inject, remove} instead of the keys above: asserts
#                        inject/remove/inject byte equality, see
#                        check_round_trip
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
    # The one scenario that reads the injected code rather than counting it.
    # RiskChecker supplies the arities the rest of the tree does not: three and
    # four parameters, an overload pair that must not share a parameter list, a
    # parameter with no name, and a method with none at all.
    #
    {
        "name": "validate: names match the arguments at every arity",
        "rule": INJECT_ALL_SRC_VALIDATE,
        "injected": ALL_SRC_FUNCTIONS,
        "injected_count": SRC_TRACE_BLOCKS,
        "remaining": SRC_TRACE_BLOCKS,
        "remaining_injected": ALL_SRC_MARKERS_WITH_VALIDATE,
        "validate_blocks": SRC_VALIDATE_BLOCKS
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
        "removed_count": SRC_TRACE_BLOCKS,
        "remaining": 0,
        "remaining_injected": 0
    },
    #
    # A remove rule says where to clean, never what: it must take out whatever
    # inject_type happened to put the block there. Counted per region, not per
    # block, so a function carrying both kinds still reports as one.
    #
    {
        "name": "remove: unfiltered rule strips validate as well as trace",
        "setup": INJECT_ALL_SRC_VALIDATE,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": ""
        },
        "removed": set(),
        "removed_count": SRC_TRACE_BLOCKS,
        "remaining": 0,
        "remaining_injected": 0
    },
    {
        "name": "remove: targeted rule strips validate as well as trace",
        "setup": INJECT_ALL_SRC_VALIDATE,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": "OnData"
        },
        "removed": {
            "OrderMgr::OnData"
        },
        "remaining": SRC_TRACE_BLOCKS - 1,
        "remaining_injected": ALL_SRC_MARKERS_WITH_VALIDATE - 3
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
        "remaining": SRC_TRACE_BLOCKS - len(ALL_RUNS)
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
        "setup_config": f"{EXAMPLES_DIR}/config_base_class_includedirs_example.json",
        "config": f"{EXAMPLES_DIR}/config_base_class_remove_example.json",
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
        "removed_count": SRC_TRACE_BLOCKS - len(ALL_RUNS),
        "remaining": len(ALL_RUNS)
    },
    #
    # Round trips. The counting scenarios above prove remove deletes enough
    # lines; these prove it deletes exactly the right ones, and that running
    # inject again on top of a remove does not stack a second copy.
    #
    #
    # The per-directory inject_type pair, run for real: test/src asks for
    # trace+validate, test/proj for trace only, and one unfiltered remove has to
    # clean both trees without being told what either rule asked for.
    #
    # setup_injected pins down what the inject half actually wrote — trace
    # everywhere plus two markers for each function under test/src that takes
    # parameters. Without it, "nothing left afterwards" would also pass if
    # inject_type had silently stopped producing validate blocks.
    #
    {
        "name": "examples: per-directory inject_type, cleaned back to nothing",
        "setup_config": f"{EXAMPLES_DIR}/config_inject_types_example.json",
        "config": f"{EXAMPLES_DIR}/config_inject_types_remove_example.json",
        "setup_injected": (
            ALL_SRC_MARKERS_WITH_VALIDATE
            +
            len(ALL_PROJ_FUNCTIONS)
        ),
        "removed": set(),
        "removed_count": (
            SRC_TRACE_BLOCKS
            +
            len(ALL_PROJ_FUNCTIONS)
        ),
        "remaining": 0,
        "remaining_injected": 0
    },
    {
        "name": "round trip: trace only",
        "round_trip": {
            "inject": INJECT_ALL_SRC,
            "remove": {
                "directory": "test/src",
                "function": ""
            }
        }
    },
    {
        "name": "round trip: trace + validate",
        "round_trip": {
            "inject": INJECT_ALL_SRC_VALIDATE,
            "remove": {
                "directory": "test/src",
                "function": ""
            }
        }
    },
    {
        "name": "round trip: trace + validate, targeted both ways",
        "round_trip": {
            "inject": {
                "directory": "test/src",
                "function": "OnData",
                "inject_type": [
                    "trace",
                    "validate"
                ]
            },
            "remove": {
                "directory": "test/src",
                "function": "OnData"
            }
        }
    },
    #
    # Byte-level proof for the shipped pair, on top of the counting scenario
    # above: both fixture trees have to come back exactly as they started.
    #
    {
        "name": "round trip: the per-directory inject_type example pair",
        "round_trip": {
            "inject": f"{EXAMPLES_DIR}/config_inject_types_example.json",
            "remove": f"{EXAMPLES_DIR}/config_inject_types_remove_example.json"
        }
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
        "trace_removed": 0,
        "includes_added": 0,
        "includes_removed": 0
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


def count_marker(marker):

    total = 0

    for path in fixture_files():
        total += path.read_text(
            encoding="utf-8"
        ).count(marker)

    return total


def count_traces():

    return count_marker(TRACE_MARKER)


def count_injected():
    """
    Every injected marker, whatever kind wrote it. A trace count alone reports
    a file as clean while a validate block is still sitting in it — which is
    exactly the state that made the next inject emit a duplicate.
    """

    return sum(
        count_marker(marker)
        for marker in INJECTED_MARKERS
    )


#
# The two-line shape a validate block has to have. Written out as a pattern
# rather than assembled from the package's own formatters, for the same reason
# INJECTED_MARKERS is: it has to be able to disagree with the tool.
#
VALIDATE_BLOCK_RE = re.compile(
    r"static const char\* __param_names\[\] = \{ (?P<names>[^}]*) \};[^\n]*\n"
    r"\s*validate_params\(\"(?P<func>[^\"]+)\", __param_names, (?P<args>[^)]*)\);"
)


def check_validate_blocks(expected_blocks):
    """
    Reads back every validate block in the fixtures and checks the quoted names
    against the arguments actually passed: same identifiers, same order, same
    count.

    Every other assertion in this file counts blocks or lines. None of them
    would notice a block that names three parameters and passes two, or names
    them in the wrong order — which is the only thing that makes the generated
    check worth generating. With one-parameter functions there was nothing to
    get wrong; the RiskChecker fixture is what gives this teeth.
    """

    failures = []
    found = 0

    for path in fixture_files():

        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()

        for match in VALIDATE_BLOCK_RE.finditer(text):

            found += 1

            names = [
                part.strip().strip('"')
                for part in match["names"].split(",")
            ]

            args = [
                part.strip()
                for part in match["args"].split(",")
            ]

            if names != args:
                failures.append(
                    f"{name}: {match['func']} names {names} "
                    f"but passes {args}"
                )

    #
    # A block whose table and call drifted apart — separated, reordered, one of
    # them missing — does not match the pattern at all, so it would go
    # uncounted rather than reported. Comparing against the raw call count
    # turns that silence into a failure.
    #
    calls = count_marker("validate_params(")

    if calls != found:
        failures.append(
            f"{calls} validate_params calls but only {found} well-formed "
            "blocks — a name table and its call are not adjacent"
        )

    if found != expected_blocks:
        failures.append(
            f"{found} validate blocks, expected {expected_blocks}"
        )

    return failures


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

    examples = sorted(
        ROOT.glob(f"{EXAMPLES_DIR}/config_*example*.json")
    )

    if not examples:
        return [
            f"no example configs found under {EXAMPLES_DIR}/ — moved or "
            "renamed? this check was passing vacuously"
        ]

    for config_file in examples:

        try:
            config = load_config(config_file)

            resolve_mode_and_rules(config)

        except Exception as error:
            failures.append(
                f"{config_file.name}: {error}"
            )

    return failures


#
# ----------------------------------------------------------------- includes
#
# Injected code references ScopeTrace and validate_params, so the file it lands
# in has to include the headers those live in. The tool adds them; the project's
# own -I is what makes them resolve.
#


def check_include_consistency():
    """
    Per file: the include is there exactly when there is injected code needing
    it, and never twice.

    Cheap enough to assert after every scenario, which is the point — it turns
    every inject scenario into a check that the include was added and every
    remove scenario into a check that it was taken away again. The two failures
    are opposites and both are quiet: without the include the file does not
    compile, and with a leftover one it drags in a header it has no use for.
    """

    failures = []

    for path in fixture_files():

        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()

        for include_line, evidence in INJECTED_INCLUDES.items():

            includes = text.count(include_line)

            blocks = sum(
                text.count(marker)
                for marker in evidence
            )

            header = include_line.split('"')[1]

            if blocks and includes != 1:
                failures.append(
                    f"{name}: {blocks} block(s) needing {header}, "
                    f"but {includes} injected include(s) of it"
                )

            if not blocks and includes:
                failures.append(
                    f"{name}: {includes} injected include(s) of {header} "
                    "with nothing left using it"
                )

    return failures


#
# A file the injector never touched, carrying exactly what it would have
# written — minus the marker comment. None of it is this tool's to delete.
#
HAND_WRITTEN_DIR = HERE / "_hand"

HAND_WRITTEN_FILE = HAND_WRITTEN_DIR / "HandRolled.cpp"

HAND_WRITTEN_SOURCE = """#include "ScopeTrace.h"

void HandRolled(
    int id
)
{
    ScopeTrace trace(
        __FILE__,
        __LINE__,
        "HandRolled"
    );

    id++;
}
"""


def check_hand_written_survives():
    """
    Hand-written code that happens to say ScopeTrace survives a remove, and an
    include already in the file is not duplicated.

    No other check here could notice either one: they all read
    `ScopeTrace trace(` as proof of an injection, so a remove that deletes
    somebody's own guard looks like a job well done. Matching on the C++ rather
    than on the marker is exactly what this tool used to do, and the README
    used to call it a feature.
    """

    failures = []

    HAND_WRITTEN_DIR.mkdir(exist_ok=True)

    HAND_WRITTEN_FILE.write_text(
        HAND_WRITTEN_SOURCE,
        encoding="utf-8"
    )

    rule = {
        "directory": "test/_hand",
        "function": ""
    }

    try:

        removes = (
            ("the whole-file remove", rule),
            (
                "a remove targeting the function",
                {**rule, "function": "HandRolled"}
            )
        )

        for what, remove_rule in removes:

            apply_rule(remove_rule, "remove")

            if HAND_WRITTEN_FILE.read_text(encoding="utf-8") != (
                HAND_WRITTEN_SOURCE
            ):

                failures.append(
                    f"{what} deleted hand-written code"
                )

                HAND_WRITTEN_FILE.write_text(
                    HAND_WRITTEN_SOURCE,
                    encoding="utf-8"
                )

        #
        # The other half: injecting into that file writes its own block, but not
        # a second copy of an include that is already there — and taking the
        # block back out leaves the hand-written include and guard alone.
        #
        apply_rule(
            {**rule, "inject_type": ["trace", "validate"]},
            "inject"
        )

        injected = HAND_WRITTEN_FILE.read_text(encoding="utf-8")

        copies = injected.count('#include "ScopeTrace.h"')

        if copies != 1:
            failures.append(
                f"{copies} copies of an include the file already had"
            )

        if "include for validate" not in injected:
            failures.append(
                "wrote a validate block without including ParameterCheck.h"
            )

        apply_rule(rule, "remove")

        if HAND_WRITTEN_FILE.read_text(encoding="utf-8") != (
            HAND_WRITTEN_SOURCE
        ):
            failures.append(
                "inject then remove did not restore the file"
            )

    finally:

        shutil.rmtree(
            HAND_WRITTEN_DIR,
            ignore_errors=True
        )

    return failures


def run_cli(config):
    """
    Drive the whole CLI over a throwaway config, the way a build step does, and
    return its exit code.

    Everything else here calls process_rule directly, which never reaches
    cli.py — so a config the CLI chokes on, or a summary line naming a stat
    nobody counts, would stay hidden until somebody ran the tool for real.
    """

    config_file = HERE / "_tmp_config.json"

    config_file.write_text(
        json.dumps(config, indent=4),
        encoding="utf-8"
    )

    argv = sys.argv

    sys.argv = [
        "trace_injector.py",
        "--config",
        str(config_file)
    ]

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return cli_main()

    finally:
        sys.argv = argv
        config_file.unlink(missing_ok=True)
        cleanup_logs()


def check_cli_round_trip(saved):
    """
    End to end through the CLI: inject, then remove, then byte-identical again.

    The inject half has to change something, or "restored" below would pass just
    as well for a run that did nothing at all.
    """

    failures = []

    restore_fixtures(saved)

    code = run_cli(
        {"inject": [INJECT_ALL_SRC_VALIDATE]}
    )

    if code != 0:
        failures.append(
            f"the inject run exited {code}"
        )

    if snapshot_fixtures() == saved:
        failures.append(
            "injected nothing, so the remove below proves nothing"
        )

    failures += check_include_consistency()

    code = run_cli(
        {
            "remove": [
                {
                    "directory": "test/src",
                    "function": ""
                }
            ]
        }
    )

    if code != 0:
        failures.append(
            f"the remove run exited {code}"
        )

    failures += diff_against(
        saved,
        "not restored by the CLI remove"
    )

    restore_fixtures(saved)

    return failures


def check_unknown_config_key():
    """
    A top-level key nothing reads is an error, not something ignored.

    This tool shipped a "headers" block that nothing read for a while, and it
    read like a feature until somebody relied on it. The same key is now the
    likeliest thing to be left in an old config, where silence would mean "your
    ParameterCheck.h is being generated" long after that stopped being true.
    """

    failures = []

    rejected = [
        (
            {
                "inject": [INJECT_ALL_SRC],
                "headers": {"types_header": "test/include/Types.h"}
            },
            "a leftover headers block"
        ),
        (
            {"inject": [INJECT_ALL_SRC], "exlude": []},
            "a typo'd exclude"
        )
    ]

    for config, what in rejected:

        try:
            resolve_mode_and_rules(config)
            failures.append(f"{what} was accepted")
        except ValueError:
            pass

    accepted = {
        "inject": [INJECT_ALL_SRC],
        "exclude": [],
        "include_dirs": ["test/proj/include"]
    }

    try:
        resolve_mode_and_rules(accepted)
    except ValueError as error:
        failures.append(
            f"every documented key together was rejected: {error}"
        )

    return failures


def check_fixtures_clean(saved=None):
    """
    The fixtures carry no injected code of any kind at rest. Before the run
    that means the previous run cleaned up after itself; after it, that this
    one did. `saved` also demands byte equality, catching debris a marker count
    misses.
    """

    failures = []

    for path in fixture_files():

        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()

        for marker in INJECTED_MARKERS:

            if marker in text:
                failures.append(
                    f"{name}: {text.count(marker)} leftover "
                    f"{marker.strip()}"
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


def apply_rule(rule, mode, include_dirs=None):

    process_rule(
        rule,
        mode,
        [],
        CaptureLogger(),
        fresh_stats(),
        include_dirs=include_dirs or []
    )


def apply_step(step, mode, include_dirs=None):
    """
    A round-trip step is either a rule dict or the path of a shipped config
    file. The config form is what lets the examples be round-tripped as
    shipped, rather than as a copy of their rules that can drift.
    """

    if isinstance(step, str):

        return apply_config(
            step,
            CaptureLogger(),
            fresh_stats()
        )

    return apply_rule(
        step,
        mode,
        include_dirs
    )


def diff_against(expected, what):

    return [
        f"{path.relative_to(ROOT).as_posix()}: {what}"
        for path, text in snapshot_fixtures().items()
        if text != expected[path]
    ]


def check_round_trip(trip, saved):
    """
    Two assertions, and the second is the one that earns its keep:

      inject -> remove                 == the original file, byte for byte
      inject -> remove -> inject       == what the first inject produced

    A remove that leaves one block of a two-block injection behind passes every
    count-based check — the file looks clean enough. Then the next inject sees
    no trace, writes a fresh block above the orphan, and you get two
    `__param_names` declarations in one scope and a file that will not compile.
    Only re-injecting and comparing catches that.
    """

    failures = []

    include_dirs = trip.get("include_dirs", [])

    restore_fixtures(saved)

    apply_step(trip["inject"], "inject", include_dirs)

    after_inject = snapshot_fixtures()

    if after_inject == saved:
        return [
            "inject changed nothing, so the round trip proves nothing"
        ]

    failures += check_include_consistency()

    apply_step(trip["remove"], "remove", include_dirs)

    failures += diff_against(
        saved,
        "not restored by remove"
    )

    apply_step(trip["inject"], "inject", include_dirs)

    failures += diff_against(
        after_inject,
        "differs after inject/remove/inject"
    )

    return failures


def run_scenario(scenario, saved):
    """Returns a list of failure descriptions (empty means the test passed)."""

    if "round_trip" in scenario:

        return check_round_trip(
            scenario["round_trip"],
            saved
        )

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

    setup_failures = []

    #
    # Asserted before the rule under test runs, because a remove scenario that
    # only checks "nothing left" passes just as well when the setup put nothing
    # there in the first place. This is what stops the setup from going quietly
    # vacuous.
    #
    if "setup_injected" in scenario:

        planted = count_injected()

        if planted != scenario["setup_injected"]:

            setup_failures.append(
                f"setup planted {planted} injected markers, "
                f"expected {scenario['setup_injected']}"
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

    failures = list(setup_failures)

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

    leftovers = [
        ("remaining", count_traces, "traces"),
        ("remaining_injected", count_injected, "injected markers")
    ]

    for key, count, what in leftovers:

        if key not in scenario:
            continue

        remaining = count()

        if remaining != scenario[key]:

            failures.append(
                f"{remaining} {what} left in the fixtures, "
                f"expected {scenario[key]}"
            )

    if "validate_blocks" in scenario:

        failures += check_validate_blocks(
            scenario["validate_blocks"]
        )

    warned = INCOMPLETE_WARNING in logger.text
    expected_warning = scenario.get("warns", False)

    if warned != expected_warning:

        failures.append(
            f"expected warning={expected_warning}, got {warned}"
        )

    #
    # Unconditional, and no scenario has to opt in: whatever a scenario was
    # written to measure, the state it leaves behind still has to be one the
    # compiler would accept.
    #
    failures += check_include_consistency()

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
            failures = run_scenario(scenario, saved)
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


def patch_remove_ignores_validate():
    """
    Put the old bug back: make every line-level check recognise ScopeTrace and
    nothing else, so a trace+validate injection loses its trace and keeps its
    validate. This is the regression the kind-blind remover exists to prevent,
    so something had better go red.
    """

    from trace_injector_pkg import line_utils

    original = line_utils.kind_of_line

    def trace_only(line):

        kind = original(line)

        return kind if kind == "trace" else None

    line_utils.kind_of_line = trace_only

    def undo():
        line_utils.kind_of_line = original

    return undo


def patch_validate_drops_last_argument():
    """
    Emit the full name table but pass one argument short of it — a validate
    block of exactly the right size and the wrong content.

    No count notices this. The block is still two lines, remove still takes it
    back out, every round trip still restores byte for byte. Only reading the
    names against the arguments does.

    Functions of one parameter are left correct on purpose: back when test/src
    had nothing wider than that, this breakage would have been invisible. It is
    the RiskChecker arities that make it show up.
    """

    from trace_injector_pkg import constants

    original = constants.INJECTION_KINDS

    def truncated(func_name, param_names):

        if not param_names:
            return []

        names = ", ".join(
            f'"{name}"'
            for name in param_names
        )

        args = ", ".join(param_names[:-1]) or param_names[0]

        return [
            f"    static const char* __param_names[] = {{ {names} }};\n",
            f'    validate_params("{func_name}", __param_names, {args});\n',
            "\n"
        ]

    patched = []

    for kind, build, markers in original:

        if kind == "validate":
            build = truncated

        patched.append(
            (kind, build, markers)
        )

    constants.INJECTION_KINDS = tuple(patched)

    def undo():
        constants.INJECTION_KINDS = original

    return undo


def patch_include_never_added():
    """
    Inject the blocks and skip the include, i.e. what this tool did until the
    project's own `-I` became the answer to where the headers live.

    Every count in this file still comes out right — the blocks are there, they
    remove cleanly, the round trips restore. The files just do not compile, and
    only check_include_consistency says so.
    """

    from trace_injector_pkg import injector

    original = injector.add_includes

    def unchanged(lines, kinds):
        return lines, []

    injector.add_includes = unchanged

    def undo():
        injector.add_includes = original

    return undo


def patch_include_never_removed():
    """
    Take the blocks out and leave the include behind.

    The opposite mistake and the quiet one: the file still compiles today, so
    nothing complains until somebody deletes ScopeTrace.h — or until the leftover
    ParameterCheck.h drags Types.h into a translation unit that stopped having
    any use for it. The byte-exact round trips are what refuse to accept it.
    """

    from trace_injector_pkg import remover

    original = remover.drop_orphan_includes

    def unchanged(lines):
        return lines, []

    remover.drop_orphan_includes = unchanged

    def undo():
        remover.drop_orphan_includes = original

    return undo


def patch_report_our_own_header():
    """
    Report the injector's own header as a parse problem, i.e. drop the one
    diagnostic log_parse_problems filters out.

    "'ScopeTrace.h' file not found" is fatal and fires on every file this tool
    has already been through, whenever the run does not happen to have the
    project's `-I` for it. Passing it on tells the reader their base_class filter
    may have matched nothing when it matched everything — and it is the only
    diagnostic clang emits for those files, so it would be all they see.
    """

    original = targets._is_our_header

    targets._is_our_header = lambda diagnostic: False

    def undo():
        targets._is_our_header = original

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
        "name": "remove blind to everything but trace",
        "patch": patch_remove_ignores_validate,
        "must_fail": [
            "remove: unfiltered rule strips validate as well as trace",
            "remove: targeted rule strips validate as well as trace",
            "round trip: trace + validate",
            "round trip: trace + validate, targeted both ways",
            #
            # The shipped pair is in here too, now that test/src is the tree
            # asking for validate: the examples have to be covered by the same
            # guard as the hand-written rules.
            #
            "examples: per-directory inject_type, cleaned back to nothing",
            "round trip: the per-directory inject_type example pair"
        ],
        "must_pass": [
            "remove: unfiltered rule strips the whole file",
            "round trip: trace only"
        ]
    },
    {
        "name": "validate arguments one short of the name table",
        "patch": patch_validate_drops_last_argument,
        "must_fail": [
            "validate: names match the arguments at every arity"
        ],
        #
        # Everything else stays green, which is the finding: a validate block
        # can be entirely wrong and still satisfy every count in this file.
        #
        "must_pass": [
            "remove: unfiltered rule strips validate as well as trace",
            "remove: targeted rule strips validate as well as trace",
            "round trip: trace + validate"
        ]
    },
    {
        "name": "blocks injected without their include",
        "patch": patch_include_never_added,
        "must_fail": [
            "same tree, relative includes, no include_dirs",
            "validate: names match the arguments at every arity",
            "round trip: trace only",
            "round trip: trace + validate"
        ],
        #
        # A rule that writes nothing needs no include, so these two stay green:
        # the check is about what was written, not about what was asked for.
        #
        "must_pass": [
            "separate include root, include_dirs MISSING -> warn, no writes",
            "remove: unfiltered rule strips the whole file"
        ]
    },
    {
        "name": "include left behind after the last block went",
        "patch": patch_include_never_removed,
        "must_fail": [
            "remove: unfiltered rule strips the whole file",
            "examples: per-directory inject_type, cleaned back to nothing",
            "round trip: trace only",
            "round trip: trace + validate",
            #
            # A partial remove notices too, and that is the interesting one: the
            # rule keeps every Run, but the files with no Run in them lose their
            # last block, and the include is per file rather than per tree.
            #
            "remove: function-level exclude keeps every Run"
        ],
        #
        # Inject-only scenarios cannot see this at all. "by function name only"
        # is the other side of the per-file rule: every file holding a Run holds
        # something else as well, so nothing there may drop its include.
        #
        "must_pass": [
            "same tree, relative includes, no include_dirs",
            "remove: by function name only"
        ]
    },
    {
        "name": "the injector's own header reported as a parse problem",
        "patch": patch_report_our_own_header,
        "must_fail": [
            "remove: by base_class, LocalCache::Execute survives",
            "examples: base_class inject then remove leaves nothing"
        ],
        #
        # Both of these parse a tree nothing has been injected into yet, so
        # there is no injected include to trip over — which is why the warning
        # they do expect is still the one they get.
        #
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
    report.record(
        "config rejects a key nothing reads",
        check_unknown_config_key()
    )

    saved = snapshot_fixtures()

    try:

        report.record(
            "hand-written ScopeTrace code is not ours to delete",
            check_hand_written_survives()
        )

        run_all_scenarios(saved, report=report.record)

        report.record(
            "the CLI injects and removes end to end",
            check_cli_round_trip(saved)
        )

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
