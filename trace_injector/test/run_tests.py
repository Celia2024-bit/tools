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
# Shared with the CLI rather than kept here: the bindings have to be pointed
# at a library they can load before anything parses, and a harness that did
# it for itself was how the CLI came to be broken without a test noticing.
#
from trace_injector_pkg.libclang_setup import configure as configure_libclang


LIBCLANG_IN_USE = configure_libclang()

from trace_injector_pkg import targets
from trace_injector_pkg.config import load_config, resolve_mode_and_rules
from trace_injector_pkg.payloads import resolve_payloads
from trace_injector_pkg.processor import process_rule

INJECTED_PREFIX = "   ✨ Injected: "
UPDATED_PREFIX = "   ✨ Updated: "
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

LEGACY_CPP = "test/legacy/Legacy.cpp"

#
# What the injector wrote before markers existed: a five-line block with
# nothing on it to say the tool put it there. Removal has to keep recognising
# this shape, or upgrading the tool orphans every trace already in a tree.
#
LEGACY_SOURCE = """#include "Legacy.h"

void Legacy::Old()
{
    ScopeTrace trace(
        __FILE__,
        __LINE__,
        __FUNCTION__
    );

    int a = 1;
}

void Legacy::New()
{
    int b = 2;
}
"""

#
# A marked line whose payload text nothing in the tool knows about. Removal
# must delete it on the strength of the marker alone; a remover still matching
# on "ScopeTrace trace(" finds nothing here.
#
ALIEN_PAYLOAD = "TotallyUnrelatedPayload(__LINE__);"

#
# A marker naming a payload the config no longer defines. Removal has to reach
# it, or deleting a payload definition strands every line it ever wrote.
#
ORPHAN_PAYLOAD = "LeftBehind();"

ORPHAN_MARKED_SOURCE = """#include "Legacy.h"

void Legacy::Old()
{
    %s  // @tj:long_gone

    int a = 1;
}

void Legacy::New()
{
    int b = 2;
}
""" % ORPHAN_PAYLOAD

#
# Two payloads, exercising every placeholder between them.
#
TWO_PAYLOADS = {
    "probe": {
        "lines": [
            "{indent}Probe(\"{qualified_name}\");"
        ]
    },
    "tag": {
        "lines": [
            "{indent}Tag(\"{class}\", \"{function}\");"
        ]
    }
}

INJECT_BOTH = {
    "directory": "test/legacy",
    "function": "Old",
    "payloads": [
        "probe",
        "tag"
    ]
}

#
# Indent, both placeholders, the marker, listed order, and the blank line that
# separates the region from the body — all in one assertion.
#
BOTH_INJECTED = (
    "{\n"
    "    Probe(\"Legacy::Old\");  // @tj:probe\n"
    "    Tag(\"Legacy\", \"Old\");  // @tj:tag\n"
    "\n"
    "    int a = 1;\n"
)

#
# A probe line that no longer matches its template, as if the template had
# been edited since. Rerunning inject has to bring it back into line, which is
# the only way to change a payload without removing it first.
#
STALE_PROBE = "Probe(\"STALE\");"

STALE_SOURCE = """#include "Legacy.h"

void Legacy::Old()
{
    %s  // @tj:probe

    int a = 1;
}

void Legacy::New()
{
    int b = 2;
}
""" % STALE_PROBE

STALE_BESIDE_TAG_SOURCE = """#include "Legacy.h"

void Legacy::Old()
{
    %s  // @tj:probe
    Tag("Legacy", "Old");  // @tj:tag

    int a = 1;
}

void Legacy::New()
{
    int b = 2;
}
""" % STALE_PROBE

#
# A payload that names the parameters it was given, which is the whole point of
# the parameter placeholders: a check that has to be handed the values cannot
# be written once and reused, it has to be generated per function.
#
#
# A payload declaring no header at all, so the line it writes does not compile:
# `Probe` is undeclared. That is an error and nothing worse, which makes this
# the one fixture left carrying a non-fatal diagnostic now that the built-in
# payload brings its own header.
#
NO_INCLUDE_PAYLOAD = {
    "probe_only": {
        "lines": [
            "{indent}Probe(\"{qualified_name}\");"
        ]
    }
}

INJECT_PROBE_ONLY = {
    "directory": "test/src",
    "base_class": "IStrategy",
    "function": "Run",
    "payloads": [
        "probe_only"
    ]
}

#
# A payload asking for a header that is nowhere on the include path. Unlike an
# undeclared name, clang treats that as fatal — which is why the include a
# payload declares has to be spelled the way the project's own sources would
# spell it.
#
UNRESOLVABLE_INCLUDE = {
    "probe_missing": {
        "lines": [
            "{indent}Probe(\"{qualified_name}\");"
        ],
        "include": "NoSuchHeaderAnywhere.h"
    }
}

INJECT_UNRESOLVABLE = {
    "directory": "test/src",
    "base_class": "IStrategy",
    "function": "Run",
    "payloads": [
        "probe_missing"
    ]
}

PARAM_CHECK = {
    "check": {
        "lines": [
            "{indent}check_count({param_count});",
            "{indent}check_all(\"{qualified_name}\", "
            "{param_name_list}, {param_names});"
        ],
        "requires_parameters": True
    }
}

INJECT_CHECK = {
    "directory": "test/params",
    "function": "",
    "payloads": [
        "check"
    ]
}

#
# The same placeholder without requires_parameters, to separate the two
# reasons a payload gets skipped. A function taking nothing renders a count of
# zero here rather than being passed over.
#
PARAM_COUNT_ONLY = {
    "count_only": {
        "lines": [
            "{indent}check_count({param_count});"
        ]
    }
}

#
# Every parameter placeholder at once, on the one method whose parameters can
# all be named.
#
CHECK_INJECTED = (
    "{\n"
    "    check_count(3);  // @tj:check\n"
    "    check_all(\"Params::Three\", {\"count\", \"price\", \"symbol\"}, "
    "count, price, symbol);  // @tj:check\n"
    "\n"
    "    (void)count;\n"
)

INJECT_ALL_KINDS = {
    "directory": "test/kinds",
    "function": ""
}

#
# Every definition under test/kinds a payload can go into. Twice is declared and
# never defined, and the two Compact bodies are written on one line, so all
# three are absent on purpose.
#
ALL_KINDS_FUNCTIONS = {
    "Kinds::Kinds",
    "Kinds::~Kinds",
    "Kinds::Emit",
    "UseEmit",
    "Thrice"
}

#
# The constructor, with the member-init list above the body. `m_limit{limit}`
# has the earlier {, so a text scan for the first one puts the payload inside
# the initialiser — which is why the body brace comes from the AST.
#
CTOR_INJECTED = (
    "    , m_limit{limit}\n"
    "{\n"
    "    ScopeTrace trace(__FILE__, __LINE__, \"Kinds::Kinds\");"
    "  // @tj:scope_trace\n"
)

#
# test/stdlib exists for one reason: <string> and <vector> bring in cursors
# whose kind ids are newer than the bindings' table, and reading .kind on one
# raises ValueError instead of returning a value.
#
INJECT_ALL_STDLIB = {
    "directory": "test/stdlib",
    "function": ""
}

ALL_STDLIB_FUNCTIONS = {
    "Stdlib::Describe",
    "Stdlib::Split",
    "Join"
}

ALIEN_MARKED_SOURCE = """#include "Legacy.h"

void Legacy::Old()
{
    int a = 1;
}

void Legacy::New()
{
    %s  // @tj:scope_trace

    int b = 2;
}
""" % ALIEN_PAYLOAD

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
#   setup_files          {relative path: text} written before anything runs,
#                        for a starting state no rule can produce
#   injected / updated /
#   removed              the EXACT set of qualified names expected in the log
#   injected_count /
#   updated_count /
#   removed_count        override the stat check, for paths that cannot name
#                        the function they touched
#   payloads             a config-level "payloads" table for this scenario
#   remaining            traces left in the fixtures afterwards
#   must_contain /
#   must_not_contain     text that must (not) be in some fixture afterwards,
#                        for payloads `remaining` does not count
#   logs / logs_absent   substrings that must (not) appear in the log
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
    },
    #
    # Markers, from both ends: a trace written before they existed still has
    # to come out, and a marked line the tool knows nothing else about still
    # has to come out.
    #
    {
        "name": "remove: pre-marker trace, targeted by function name",
        "setup_files": {
            LEGACY_CPP: LEGACY_SOURCE
        },
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": "Old"
        },
        "removed": {
            "Legacy::Old"
        },
        "remaining": 0
    },
    {
        "name": "remove: pre-marker trace, unfiltered whole-file scan",
        "setup_files": {
            LEGACY_CPP: LEGACY_SOURCE
        },
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": ""
        },
        "removed": set(),
        "removed_count": 1,
        "remaining": 0
    },
    {
        "name": "inject does not stack on top of a pre-marker trace",
        "setup_files": {
            LEGACY_CPP: LEGACY_SOURCE
        },
        "rule": {
            "directory": "test/legacy",
            "function": "Old"
        },
        "injected": set(),
        "remaining": 1
    },
    {
        "name": "remove: found by marker, not by payload text",
        "setup_files": {
            LEGACY_CPP: ALIEN_MARKED_SOURCE
        },
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": "New"
        },
        "removed": {
            "Legacy::New"
        },
        "must_not_contain": [
            ALIEN_PAYLOAD
        ]
    },
    #
    # Configurable payloads. The built-in scope_trace must stay out of the
    # way when a rule names its own, which is why `remaining` is 0 in the
    # inject scenarios below.
    #
    {
        "name": "payloads: listed order, indent and every placeholder",
        "payloads": TWO_PAYLOADS,
        "rule": INJECT_BOTH,
        "injected": {
            "Legacy::Old"
        },
        "remaining": 0,
        "must_contain": [
            BOTH_INJECTED
        ]
    },
    {
        "name": "payloads: rerun injects only what is missing",
        "payloads": TWO_PAYLOADS,
        "setup": {
            "directory": "test/legacy",
            "function": "Old",
            "payloads": [
                "probe"
            ]
        },
        "rule": INJECT_BOTH,
        "injected": {
            "Legacy::Old"
        },
        "must_contain": [
            BOTH_INJECTED
        ]
    },
    {
        "name": "remove: a named payload, leaving the other in place",
        "payloads": TWO_PAYLOADS,
        "setup": INJECT_BOTH,
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": "Old",
            "payloads": [
                "probe"
            ]
        },
        "removed": {
            "Legacy::Old"
        },
        "must_contain": [
            "{\n    Tag(\"Legacy\", \"Old\");  // @tj:tag\n\n    int a = 1;\n"
        ],
        "must_not_contain": [
            "Probe("
        ]
    },
    {
        "name": "remove: no payloads listed reaches an orphaned marker",
        "setup_files": {
            LEGACY_CPP: ORPHAN_MARKED_SOURCE
        },
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": "Old"
        },
        "removed": {
            "Legacy::Old"
        },
        "must_not_contain": [
            ORPHAN_PAYLOAD
        ]
    },
    {
        "name": "remove: payloads listed spares a marker not among them",
        "setup_files": {
            LEGACY_CPP: ORPHAN_MARKED_SOURCE
        },
        "mode": "remove",
        "rule": {
            "directory": "test/legacy",
            "function": "Old",
            "payloads": [
                "scope_trace"
            ]
        },
        "removed": set(),
        "must_contain": [
            ORPHAN_PAYLOAD
        ]
    },
    #
    # Editing a payload template and rerunning inject is the only way to
    # change what is already in the tree without removing it first, so the
    # injected region is rebuilt rather than skipped on sight.
    #
    {
        "name": "payloads: a stale line is re-rendered, not skipped",
        "payloads": TWO_PAYLOADS,
        "setup_files": {
            LEGACY_CPP: STALE_SOURCE
        },
        "rule": {
            "directory": "test/legacy",
            "function": "Old",
            "payloads": [
                "probe"
            ]
        },
        "injected": set(),
        "updated": {
            "Legacy::Old"
        },
        "must_contain": [
            "{\n    Probe(\"Legacy::Old\");  // @tj:probe\n\n    int a = 1;\n"
        ],
        "must_not_contain": [
            STALE_PROBE
        ]
    },
    {
        "name": "payloads: rebuilding keeps a payload the rule does not own",
        "payloads": TWO_PAYLOADS,
        "setup_files": {
            LEGACY_CPP: STALE_BESIDE_TAG_SOURCE
        },
        "rule": {
            "directory": "test/legacy",
            "function": "Old",
            "payloads": [
                "probe"
            ]
        },
        "updated": {
            "Legacy::Old"
        },
        "must_contain": [
            BOTH_INJECTED
        ]
    },
    {
        "name": "payloads: an up-to-date region is left exactly alone",
        "payloads": TWO_PAYLOADS,
        "setup": INJECT_BOTH,
        "rule": INJECT_BOTH,
        "injected": set(),
        "updated": set(),
        "remaining": 0,
        "must_contain": [
            BOTH_INJECTED
        ]
    },
    #
    # Parameters. Three of the four methods under test/params cannot be handed
    # to a check, each for its own reason, and the difference between silence
    # and a warning is the point: one is the config getting what it asked for,
    # the others are a check quietly not happening.
    #
    {
        "name": "params: every placeholder, and the three functions skipped",
        "payloads": PARAM_CHECK,
        "rule": INJECT_CHECK,
        "injected": {
            "Params::Three"
        },
        "must_contain": [
            CHECK_INJECTED
        ],
        "logs": [
            "check skipped: Params::Unnamed() has an unnamed parameter",
            "check skipped: Params::Variadic() is variadic"
        ],
        "logs_absent": [
            #
            # requires_parameters skipping a function that takes none is the
            # rule working, so it says nothing at all.
            #
            "Params::Nothing"
        ]
    },
    {
        "name": "params: requires_parameters is what skips, not the placeholder",
        "payloads": PARAM_COUNT_ONLY,
        "rule": {
            "directory": "test/params",
            "function": "",
            "payloads": [
                "count_only"
            ]
        },
        "injected": {
            "Params::Three",
            "Params::Nothing"
        },
        "must_contain": [
            "    check_count(3);  // @tj:count_only\n",
            "    check_count(0);  // @tj:count_only\n"
        ],
        "logs": [
            "count_only skipped: Params::Unnamed() has an unnamed parameter",
            "count_only skipped: Params::Variadic() is variadic"
        ]
    },
    {
        "name": "params: a payload naming no parameter goes in everywhere",
        "rule": {
            "directory": "test/params",
            "function": ""
        },
        "injected": {
            "Params::Three",
            "Params::Unnamed",
            "Params::Nothing",
            "Params::Variadic"
        },
        "remaining": 4
    },
    {
        "name": "remove: a parameter payload comes out by marker like any other",
        "payloads": PARAM_CHECK,
        "setup": INJECT_CHECK,
        "mode": "remove",
        "rule": {
            "directory": "test/params",
            "function": "Three"
        },
        "removed": {
            "Params::Three"
        },
        "must_not_contain": [
            "check_all",
            "check_count"
        ]
    },
    #
    # Includes. The header the payload needs is added on inject and taken back
    # out once nothing in the file needs it, which is what lets a file the
    # tool has touched still parse on the next run.
    #
    {
        "name": "includes: the built-in header is added once per file",
        "rule": INJECT_ALL_SRC,
        "injected": ALL_SRC_FUNCTIONS,
        "must_contain": [
            "#include \"NetworkMgr.h\"\n"
            "#include \"ScopeTrace.h\"  // @tj:scope_trace\n"
        ],
        "logs": [
            "➕ Include: #include \"ScopeTrace.h\"  // @tj:scope_trace"
        ]
    },
    {
        "name": "includes: a rerun does not add a second copy",
        "setup": INJECT_ALL_SRC,
        "rule": INJECT_ALL_SRC,
        "injected": set(),
        "updated": set(),
        "logs_absent": [
            "➕ Include:"
        ]
    },
    {
        "name": "includes: removed once the last payload in the file is gone",
        "setup": INJECT_ALL_SRC,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": ""
        },
        "removed": set(),
        "removed_count": len(ALL_SRC_FUNCTIONS),
        "remaining": 0,
        "must_not_contain": [
            "ScopeTrace.h"
        ],
        "logs": [
            "➖ Include: #include \"ScopeTrace.h\"  // @tj:scope_trace"
        ]
    },
    {
        "name": "includes: kept while another function in the file still needs it",
        "setup": INJECT_ALL_SRC,
        "mode": "remove",
        "rule": {
            "directory": "test/src",
            "function": "Run"
        },
        "removed": ALL_RUNS,
        "must_contain": [
            "#include \"ScopeTrace.h\"  // @tj:scope_trace\n"
        ]
    },
    {
        "name": "includes: a payload declaring none leaves code that will not compile",
        "payloads": NO_INCLUDE_PAYLOAD,
        "setup": INJECT_PROBE_ONLY,
        "mode": "remove",
        "rule": INJECT_PROBE_ONLY,
        "removed": {
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        },
        #
        # An undeclared name is an error and no more, so base-class matching is
        # unaffected and there is nothing to warn about.
        #
        "warns": False
    },
    {
        "name": "includes: an unresolvable header round-trips, warning on the way",
        "payloads": UNRESOLVABLE_INCLUDE,
        "setup": INJECT_UNRESOLVABLE,
        "mode": "remove",
        "rule": INJECT_UNRESOLVABLE,
        "removed": {
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        },
        "must_not_contain": [
            "NoSuchHeaderAnywhere.h"
        ],
        #
        # A header clang cannot find is fatal, so the next run's base-class
        # matching is no longer trustworthy — the reason to spell the include
        # the way the project's own sources spell it.
        #
        "warns": True
    },
    #
    # Kinds of definition. A constructor, a destructor and a template are all
    # functions with bodies, and each one breaks a different assumption: the
    # constructor has braces before its body, the template has no body at all
    # until something instantiates it.
    #
    {
        "name": "kinds: constructor, destructor and template all take a payload",
        "rule": INJECT_ALL_KINDS,
        "injected": ALL_KINDS_FUNCTIONS,
        "must_contain": [
            CTOR_INJECTED
        ]
    },
    {
        "name": "kinds: the trace names the class, not just the function",
        "rule": INJECT_ALL_KINDS,
        "injected": ALL_KINDS_FUNCTIONS,
        #
        # __FUNCTION__ would give `Emit` and `~Kinds` on gcc, with nothing to
        # say which class, and something else again on MSVC. A free function
        # has no class to add, and reads the same either way.
        #
        "must_contain": [
            "ScopeTrace trace(__FILE__, __LINE__, \"Kinds::Emit\");",
            "ScopeTrace trace(__FILE__, __LINE__, \"Kinds::~Kinds\");",
            "ScopeTrace trace(__FILE__, __LINE__, \"UseEmit\");"
        ],
        "must_not_contain": [
            "__FUNCTION__"
        ]
    },
    {
        "name": "kinds: the member-init list is not mistaken for the body",
        "rule": INJECT_ALL_KINDS,
        "injected": ALL_KINDS_FUNCTIONS,
        #
        # Nothing at all between the last initialiser and the brace. Scanning
        # the text for the first { lands on `m_limit{limit}` and splits these
        # two lines apart, which is what this asserts did not happen.
        #
        "must_contain": [
            "    , m_limit{limit}\n{\n"
        ]
    },
    {
        "name": "kinds: a template nothing instantiates is still found",
        "rule": {
            "directory": "test/kinds",
            "function": "Thrice"
        },
        "injected": {
            "Thrice"
        },
        #
        # Twice, declared and never defined, is the reason the text fallback
        # stops at a ; — the two look alike until the line after the signature.
        #
        "must_contain": [
            "T Twice(T x);\n\ntemplate <typename T>\nT Thrice(T x)\n"
        ]
    },
    {
        "name": "kinds: a body on one line is reported and left alone",
        "rule": INJECT_ALL_KINDS,
        "injected": ALL_KINDS_FUNCTIONS,
        "must_contain": [
            "Compact::Compact() { }\n",
            "void Compact::Tick() { return; }\n"
        ],
        "logs": [
            "Compact::Compact() skipped: body is on one line",
            "Compact::Tick() skipped: body is on one line"
        ]
    },
    {
        "name": "kinds: every payload put in comes back out",
        "setup": INJECT_ALL_KINDS,
        "mode": "remove",
        "rule": {
            "directory": "test/kinds",
            "function": ""
        },
        "removed": set(),
        "removed_count": len(ALL_KINDS_FUNCTIONS),
        "remaining": 0,
        "must_not_contain": [
            "ScopeTrace.h"
        ]
    },
    {
        "name": "kinds: a destructor's payload comes out by name",
        "setup": INJECT_ALL_KINDS,
        "mode": "remove",
        "rule": {
            "directory": "test/kinds",
            "function": "~Kinds"
        },
        "removed": {
            "Kinds::~Kinds"
        },
        #
        # The other four are still there, so the include stays.
        #
        "remaining": len(ALL_KINDS_FUNCTIONS) - 1,
        "must_contain": [
            "#include \"ScopeTrace.h\"  // @tj:scope_trace\n"
        ]
    },
    #
    # Standard library headers. Not a feature — a fixture that reaches the
    # cursor kinds the bindings cannot name, which every real .cpp does and no
    # other fixture here did.
    #
    {
        "name": "stdlib: a file including <string> is injected, not crashed on",
        "rule": INJECT_ALL_STDLIB,
        "injected": ALL_STDLIB_FUNCTIONS,
        "must_contain": [
            "ScopeTrace trace(__FILE__, __LINE__, \"Stdlib::Split\");"
        ]
    },
    {
        "name": "stdlib: and comes back out again",
        "setup": INJECT_ALL_STDLIB,
        "mode": "remove",
        "rule": {
            "directory": "test/stdlib",
            "function": ""
        },
        "removed": set(),
        "removed_count": len(ALL_STDLIB_FUNCTIONS),
        "remaining": 0
    },
    {
        "name": "examples: the parameter check example names what it can",
        "config": "config_param_check_example.json",
        "injected": {
            "Params::Three"
        },
        "must_contain": [
            "    check_all(\"Params::Three\", "
            "{\"count\", \"price\", \"symbol\"}, count, price, symbol);"
            "  // @tj:check_parameters\n",
            "#include \"ParameterCheck.h\"  // @tj:check_parameters\n"
        ]
    },
    {
        "name": "examples: the payloads example writes both, in order",
        "config": "config_payloads_example.json",
        "injected": {
            "StrategyEngine::Run",
            "AlphaStrategy::Run"
        },
        "remaining": 2,
        "must_contain": [
            "    ScopeTrace trace(__FILE__, __LINE__, \"AlphaStrategy::Run\");"
            "  // @tj:scope_trace\n"
            "    LOG(INFO) << \"-> AlphaStrategy::Run\";  // @tj:enter_exit\n"
        ]
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
        "trace_updated": 0,
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


#
# Configs that must be rejected. Every one of these fails silently if it is
# accepted: an undefined payload injects nothing and reports no changes
# required, and a name carrying the marker text makes the line unremovable.
#
BAD_CONFIGS = [
    (
        "rule names an undefined payload",
        {
            "inject": [
                {
                    "directory": "x",
                    "payloads": [
                        "nope"
                    ]
                }
            ]
        }
    ),
    (
        "payload with no lines",
        {
            "inject": [],
            "payloads": {
                "p": {}
            }
        }
    ),
    (
        "payloads is a list, not an object",
        {
            "inject": [],
            "payloads": [
                "p"
            ]
        }
    ),
    (
        "payload line is not a string",
        {
            "inject": [],
            "payloads": {
                "p": {
                    "lines": [
                        42
                    ]
                }
            }
        }
    ),
    (
        "payload name carries the marker text",
        {
            "inject": [],
            "payloads": {
                "p // @tj:q": {
                    "lines": [
                        "x"
                    ]
                }
            }
        }
    ),
    (
        "requires_parameters is not a bool",
        {
            "inject": [],
            "payloads": {
                "p": {
                    "lines": [
                        "x"
                    ],
                    "requires_parameters": "yes"
                }
            }
        }
    ),
    (
        "include is neither a header nor a list of them",
        {
            "inject": [],
            "payloads": {
                "p": {
                    "lines": [
                        "x"
                    ],
                    "include": 42
                }
            }
        }
    ),
    (
        "include lists an empty header name",
        {
            "inject": [],
            "payloads": {
                "p": {
                    "lines": [
                        "x"
                    ],
                    "include": [
                        "a.h",
                        "  "
                    ]
                }
            }
        }
    )
]


def check_config_rejections():

    failures = []

    for description, config in BAD_CONFIGS:

        try:
            resolve_mode_and_rules(config)

        except ValueError:
            continue

        except Exception as error:
            failures.append(
                f"{description}: raised {type(error).__name__}, "
                "expected ValueError"
            )
            continue

        failures.append(
            f"{description}: accepted"
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

    (
        mode,
        rules,
        exclude_rules,
        include_dirs,
        payload_table
    ) = resolve_mode_and_rules(
        load_config(ROOT / config_file)
    )

    for rule in rules:

        process_rule(
            rule,
            mode,
            exclude_rules,
            logger,
            stats,
            include_dirs=include_dirs,
            payload_table=payload_table
        )


def run_scenario(scenario):
    """Returns a list of failure descriptions (empty means the test passed)."""

    for relative, text in scenario.get("setup_files", {}).items():

        (ROOT / relative).write_text(
            text,
            encoding="utf-8"
        )

    payload_table = resolve_payloads(
        {
            "payloads": scenario.get("payloads")
        }
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
            include_dirs=scenario.get("setup_include_dirs", []),
            payload_table=payload_table
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
            include_dirs=scenario.get("include_dirs", []),
            payload_table=payload_table
        )

    failures = []

    checks = [
        ("injected", INJECTED_PREFIX, "trace_injected"),
        ("updated", UPDATED_PREFIX, "trace_updated"),
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

    for needle in scenario.get("must_not_contain", []):

        left = [
            path.relative_to(ROOT).as_posix()
            for path in fixture_files()
            if needle in path.read_text(encoding="utf-8")
        ]

        if left:

            failures.append(
                f"{needle!r} still present in {', '.join(left)}"
            )

    for needle in scenario.get("must_contain", []):

        found = any(
            needle in path.read_text(encoding="utf-8")
            for path in fixture_files()
        )

        if not found:

            failures.append(
                f"not found in any fixture:\n"
                + "\n".join(
                    f"      | {line}"
                    for line in needle.splitlines()
                )
            )

    for needle in scenario.get("logs", []):

        if needle not in logger.text:

            failures.append(
                f"not logged: {needle!r}"
            )

    for needle in scenario.get("logs_absent", []):

        if needle in logger.text:

            failures.append(
                f"logged but should not have been: {needle!r}"
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


def patch_function(name, replacement, module_names):
    """
    Swap a function in every module that imported it by name. `from x import
    f` binds f in the importer, so patching x alone leaves the callers holding
    the original.
    """

    import importlib

    modules = [
        importlib.import_module(f"trace_injector_pkg.{module_name}")
        for module_name in module_names
    ]

    originals = [
        getattr(module, name)
        for module in modules
    ]

    for module in modules:
        setattr(module, name, replacement)

    def undo():

        for module, original in zip(modules, originals):
            setattr(module, name, original)

    return undo


def patch_drop_legacy_fallback():
    """Recognise marked payloads only, forgetting the pre-marker layout."""

    return patch_function(
        "find_legacy_trace_line",
        lambda lines, brace_idx: None,
        ["line_utils", "remover", "injector"]
    )


def patch_blind_to_markers():
    """Stop reading the marker, leaving removal to match on payload text."""

    return patch_function(
        "marker_of",
        lambda line: None,
        ["line_utils", "remover"]
    )


def patch_ignore_rule_payloads():
    """Act as if no rule ever named a payload of its own."""

    from trace_injector_pkg.constants import SCOPE_TRACE

    return patch_function(
        "payloads_for_rule",
        lambda rule, mode, table: [SCOPE_TRACE],
        ["payloads", "processor"]
    )


def patch_render_verbatim():
    """Emit templates unsubstituted, so every placeholder stays literal."""

    from trace_injector_pkg.constants import MARKER_PREFIX

    def verbatim(name, spec, context):

        return [
            f"{template}  {MARKER_PREFIX}{name}\n"
            for template in spec["lines"]
        ]

    return patch_function(
        "render",
        verbatim,
        ["payloads", "injector"]
    )


def patch_span_blind():
    """Stop seeing the region already at the top of a body."""

    return patch_function(
        "injected_span",
        lambda lines, brace_idx: (brace_idx + 1, brace_idx + 1),
        ["line_utils", "injector"]
    )


def patch_include_never_orphaned():
    """Keep every injected #include, whether anything still needs it or not."""

    return patch_function(
        "orphaned_include_lines",
        lambda lines: [],
        ["line_utils", "remover"]
    )


def patch_include_blind():
    """Stop noticing an #include that is already in the file."""

    return patch_function(
        "has_include",
        lambda lines, directive: False,
        ["line_utils", "injector"]
    )


def patch_never_skip():
    """Render every payload into every function, parameters or not."""

    return patch_function(
        "skip_reason",
        lambda spec, node: (None, False),
        ["payloads", "injector"]
    )


def patch_brace_from_text():
    """
    Find the body brace by scanning the text from the signature, the way this
    worked before constructors were in scope. Every ordinary function is
    unaffected; a member-init list is not.
    """

    from trace_injector_pkg.line_utils import scan_for_body_brace

    return patch_function(
        "body_open_brace",
        lambda node, lines: scan_for_body_brace(
            lines,
            node.extent.start.line
        ),
        ["targets", "injector", "remover"]
    )


def patch_one_line_blind():
    """Treat a body written on one line as if it had room for a payload."""

    return patch_function(
        "is_one_line_body",
        lambda lines, brace_idx: False,
        ["line_utils", "injector"]
    )


def patch_kind_read_unguarded():
    """
    Read cursor.kind directly, the way this did before the guard. Any fixture
    that stays inside its own headers is unaffected; one that includes <string>
    reaches a kind the bindings cannot name and the read raises.
    """

    return patch_function(
        "kind_of",
        lambda cursor: cursor.kind,
        ["cursors", "targets", "class_hierarchy"]
    )


def patch_payload_uses_function_macro():
    """
    Put __FUNCTION__ back in the built-in payload, the way it read before the
    real ScopeTrace existed. Every other scenario is unaffected: the marker is
    what removal reads, and the include is unchanged.
    """

    return patch_function(
        "BUILT_IN_PAYLOADS",
        {
            "scope_trace": {
                "lines": [
                    "{indent}ScopeTrace trace("
                    "__FILE__, __LINE__, __FUNCTION__);"
                ],
                "include": "ScopeTrace.h"
            }
        },
        ["payloads", "injector", "processor"]
    )


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
            "includes: a payload declaring none leaves code that will not compile"
        ],
        "must_pass": [
            "separate include root, include_dirs given",
            "separate include root, include_dirs MISSING -> warn, no writes",
            #
            # Injecting the #include is what makes an already-injected file
            # parse cleanly on the second pass, so there is nothing left here
            # for a widened threshold to find.
            #
            "remove: by base_class, LocalCache::Execute survives",
            "examples: base_class inject then remove leaves nothing"
        ]
    },
    {
        "name": "legacy fallback dropped",
        "patch": patch_drop_legacy_fallback,
        "must_fail": [
            "remove: pre-marker trace, targeted by function name",
            "inject does not stack on top of a pre-marker trace"
        ],
        "must_pass": [
            #
            # The unfiltered scan matches the legacy text itself, so it is
            # deliberately not affected — the fallback that just vanished is
            # the targeted one.
            #
            "remove: pre-marker trace, unfiltered whole-file scan",
            "remove: by function name only"
        ]
    },
    {
        "name": "blind to markers",
        "patch": patch_blind_to_markers,
        "must_fail": [
            "remove: found by marker, not by payload text",
            "remove: by function name only"
        ],
        "must_pass": [
            "same tree, relative includes, no include_dirs",
            "remove: pre-marker trace, targeted by function name"
        ]
    },
    {
        "name": "rule payload list ignored",
        "patch": patch_ignore_rule_payloads,
        "must_fail": [
            "payloads: listed order, indent and every placeholder",
            "payloads: rerun injects only what is missing",
            "remove: a named payload, leaving the other in place",
            "remove: no payloads listed reaches an orphaned marker"
        ],
        "must_pass": [
            #
            # This rule already names scope_trace and nothing else, so
            # forcing that list changes nothing about it.
            #
            "remove: payloads listed spares a marker not among them",
            "remove: by function name only"
        ]
    },
    {
        "name": "placeholders left unsubstituted",
        "patch": patch_render_verbatim,
        "must_fail": [
            "payloads: listed order, indent and every placeholder",
            "remove: a named payload, leaving the other in place"
        ],
        "must_pass": [
            #
            # The built-in payload still contains "ScopeTrace trace(" with
            # {indent} left literal, so nothing counting traces notices.
            #
            "same tree, relative includes, no include_dirs",
            "remove: by function name only"
        ]
    },
    {
        "name": "injected region no longer recognised",
        "patch": patch_span_blind,
        "must_fail": [
            "payloads: a stale line is re-rendered, not skipped",
            "payloads: rebuilding keeps a payload the rule does not own",
            "payloads: an up-to-date region is left exactly alone",
            "payloads: rerun injects only what is missing"
        ],
        "must_pass": [
            #
            # Nothing is at the top of a clean body, and the pre-marker path
            # never consulted the span.
            #
            "same tree, relative includes, no include_dirs",
            "remove: pre-marker trace, targeted by function name"
        ]
    },
    {
        "name": "injected includes never taken back out",
        "patch": patch_include_never_orphaned,
        "must_fail": [
            "includes: removed once the last payload in the file is gone",
            "includes: an unresolvable header round-trips, warning on the way"
        ],
        "must_pass": [
            #
            # This one keeps its include either way, so there is nothing here
            # for the missing cleanup to get wrong.
            #
            "includes: kept while another function in the file still needs it",
            "remove: by function name only"
        ]
    },
    {
        "name": "blind to an include already there",
        "patch": patch_include_blind,
        "must_fail": [
            "includes: a rerun does not add a second copy"
        ],
        "must_pass": [
            #
            # Nothing is there to be noticed on a clean file, so the first
            # inject is unaffected.
            #
            "includes: the built-in header is added once per file",
            "same tree, relative includes, no include_dirs"
        ]
    },
    {
        "name": "parameters never stand in the way",
        "patch": patch_never_skip,
        "must_fail": [
            "params: every placeholder, and the three functions skipped",
            "params: requires_parameters is what skips, not the placeholder"
        ],
        "must_pass": [
            #
            # Nothing here asks about parameters, so there was never a skip to
            # take away.
            #
            "params: a payload naming no parameter goes in everywhere",
            "payloads: listed order, indent and every placeholder"
        ]
    },
    {
        "name": "body brace found by text instead of by AST",
        "patch": patch_brace_from_text,
        "must_fail": [
            "kinds: the member-init list is not mistaken for the body",
            "kinds: constructor, destructor and template all take a payload"
        ],
        "must_pass": [
            #
            # A function with no member-init list has its body brace as the
            # first one after the signature either way.
            #
            "same tree, relative includes, no include_dirs",
            "kinds: a template nothing instantiates is still found"
        ]
    },
    {
        "name": "one-line bodies treated as roomy",
        "patch": patch_one_line_blind,
        "must_fail": [
            "kinds: a body on one line is reported and left alone"
        ],
        "must_pass": [
            #
            # Every other fixture writes its braces on their own lines, so
            # there is nothing here for the missing guard to spoil.
            #
            "kinds: a template nothing instantiates is still found",
            "params: a payload naming no parameter goes in everywhere"
        ]
    },
    {
        "name": "cursor kinds read without the guard",
        "patch": patch_kind_read_unguarded,
        "must_fail": [
            "stdlib: a file including <string> is injected, not crashed on",
            "stdlib: and comes back out again"
        ],
        "must_pass": [
            #
            # Every other fixture stays inside headers it wrote itself, which
            # is exactly why this crash survived so long.
            #
            "same tree, relative includes, no include_dirs",
            "kinds: constructor, destructor and template all take a payload"
        ]
    },
    {
        "name": "built-in payload back to __FUNCTION__",
        "patch": patch_payload_uses_function_macro,
        "must_fail": [
            "kinds: the trace names the class, not just the function",
            "kinds: constructor, destructor and template all take a payload",
            "examples: the payloads example writes both, in order"
        ],
        "must_pass": [
            #
            # Removal never reads the payload's text, so a different payload
            # comes out exactly the same way.
            #
            "kinds: every payload put in comes back out",
            "kinds: a destructor's payload comes out by name"
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
        "broken configs are rejected",
        check_config_rejections()
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
