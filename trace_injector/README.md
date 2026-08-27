# Trace Injector

Inserts (or strips) a `ScopeTrace` guard at the top of C++ function bodies,
driven by `config.json`. Function boundaries come from libclang's AST, not
from regex, so overloads and multi-line signatures are handled correctly.

```
python trace_injector.py --config config.json
```

Log lines name each function by its fully qualified name, so overrides that
share a method name stay distinguishable:

```
✨ Injected: StrategyEngine::Run()
✨ Injected: AlphaStrategy::Run()
✨ Injected: util::Reset()          free function, namespace only
✨ Injected: Normalize()            free function at file scope
```

## What gets injected

By default one line at the top of the body, ending in a marker:

```cpp
void AlphaStrategy::Run()
{
    ScopeTrace trace(__FILE__, __LINE__, __FUNCTION__);  // @tj:scope_trace

    ...
}
```

The marker is what `remove` looks for. It names the payload that produced the
line, so removal never has to recognise the payload's own text — leave the
marker alone and an injected line stays removable however it is later worded.

Traces written by earlier versions of the tool carry no marker (they were a
five-line block). `remove` still recognises that shape, and `inject` still
counts it as present rather than stacking a second trace on top, so there is
nothing to migrate.

What actually goes on the line is configurable — see **Payloads** below.

## Config

Top level holds exactly one of `inject` or `remove` (never both), plus the
optional `exclude`, `include_dirs` and `payloads` keys.

```json
{
    "inject": [
        {
            "directory": "src/strategy",
            "file": "",
            "base_class": "IStrategy",
            "function": "Run"
        }
    ],

    "exclude": [
        { "directory": "src/strategy", "file": "StrategyEngine.cpp", "function": "Run" }
    ],

    "include_dirs": [ "include" ]
}
```

### Rule fields

Four of them are filters, ANDed together. An empty (or absent) field means
"no restriction on this dimension". Both modes accept all four: whatever an
`inject` rule can put in, the same rule under `remove` takes back out. A
fifth, `payloads`, says *what* to write rather than where — see below.

| Field | Meaning | Empty means |
|---|---|---|
| `directory` | Root to scan for `.cpp` files, recursively | current directory |
| `file` | Only `.cpp` files with this exact name | every `.cpp` found |
| `function` | Only functions with this exact name | every function |
| `base_class` | Only methods of a class that IS this class or derives from it, at any depth | no hierarchy filter |

`base_class` is for the "I don't know who implements/calls this virtual
function" case: name the base class and the tool finds every override down
the whole hierarchy, wherever those files happen to live.

Two things to know about it:

- **is-a semantics.** `"base_class": "A"` matches `A` itself as well as its
  descendants — when you are hunting for who calls a virtual function, `A`'s
  own implementation is a candidate too.
- **Access specifier is ignored.** `class B : private A` matches just like
  `class B : public A`. Private inheritance still overrides the virtual and
  still dispatches, so skipping it risks a silent miss.

`base_class` is rejected in `exclude` entries only — excluding works at the
directory/file/function level.

### Payloads

A payload is a name plus a list of line templates. Define your own in the
top-level `payloads` table and name them in a rule:

```json
{
    "inject": [
        {
            "directory": "test/src",
            "base_class": "IStrategy",
            "function": "Run",
            "payloads": [ "scope_trace", "enter_exit" ]
        }
    ],

    "payloads": {
        "enter_exit": {
            "lines": [ "{indent}LOG(INFO) << \"-> {qualified_name}\";" ]
        }
    }
}
```

which writes, in the order listed:

```cpp
void AlphaStrategy::Run()
{
    ScopeTrace trace(__FILE__, __LINE__, __FUNCTION__);  // @tj:scope_trace
    LOG(INFO) << "-> AlphaStrategy::Run";  // @tj:enter_exit

    ...
}
```

`scope_trace` is built in, so it needs no definition. Redefine it by name if
you want a different trace; a name not already in the table adds a payload.

Placeholders in a template:

| Placeholder | Is |
|---|---|
| `{indent}` | the body's indentation — the brace line's own, plus four |
| `{qualified_name}` | `trading::AlphaStrategy::Run` |
| `{function}` | `Run` |
| `{class}` | `trading::AlphaStrategy`, empty for a free function |
| `{param_names}` | `count, price, symbol` — ready to pass along |
| `{param_name_list}` | `{"count", "price", "symbol"}` — the names as strings |
| `{param_count}` | `3` |

Templates go through Python's `str.format`, so a literal brace has to be
doubled: `if (x) {{` . Leave the trailing newline off — the tool appends the
marker and the newline itself.

**Parameters.** A payload that names its parameters cannot always be written.
Three cases, and the tool treats them differently:

| The function | What happens |
|---|---|
| takes parameters, all named | injected |
| takes none, and the payload sets `"requires_parameters": true` | skipped, silently — the config asked for exactly this |
| has an unnamed parameter (`void f(int)`) | skipped, **with a warning** |
| is variadic (`void f(const char*, ...)`) | skipped, **with a warning** |

The last two are refusals about naming, not about types. An unnamed parameter
cannot be passed along, and a variadic tail cannot be enumerated at all — a
template expanding to `check_all(..., a, b)` would silently ignore everything
after `b`, which is worse than not injecting. That is a check you asked for and
will not get, so it goes in the log:

```
⚠️  check_parameters skipped: Params::Unnamed() has an unnamed parameter
⚠️  check_parameters skipped: Params::Variadic() is variadic
```

`requires_parameters` is a separate switch, and only about the empty case. Set
it when the payload makes no sense for a function taking nothing; leave it off
and `{param_count}` renders `0` and `{param_name_list}` renders `{}`. Both
warnings apply either way — they are triggered by the placeholders, not by the
flag. See `config_param_check_example.json`.

**Editing a template.** Change one and rerun `inject`: the region at the top
of each matching body is rebuilt from the templates, so the lines come out
right without a `remove` pass first. The log distinguishes the two:

```
✨ Injected: AlphaStrategy::Run()   a payload that was not there
✨ Updated: AlphaStrategy::Run()    a payload whose text had drifted
✅ Already injected: AlphaStrategy::Run()
```

Payloads the rule does not name are copied through untouched, so rebuilding
for one never disturbs another sitting beside it.

**Which payloads a rule acts on when it does not say:**

- `inject` → `scope_trace` alone, so a config written before payloads existed
  keeps injecting exactly what it always did. Adding a definition to the table
  changes nothing until a rule names it.
- `remove` → every marker it finds, whether or not the table still defines a
  payload by that name. Cleaning up is the one job where forgetting to list
  something should not leave it behind, and it is the only way to reach lines
  whose payload definition has since left the config. Name payloads
  explicitly to remove just those and spare the rest.

### What `remove` removes

`remove` mirrors `inject`, with one deliberate asymmetry:

- **Any filter present** (`function`, `base_class`, or a matching `exclude`)
  → the file is parsed and only the marked lines at the top of the selected
  functions are deleted. Same selection pass as `inject`, so the same rule
  takes back out exactly what it put in, and the log names each function it
  removed from.
- **No filter at all** → no parsing, just a line scan that strips *every*
  marked line in the matched files, wherever it sits. Slightly blunter, but
  it also catches traces the current rules no longer select — left over from
  a rule you have since edited. The log cannot name the function in this
  case, since there is no AST to ask.

### `directory` vs `include_dirs`

These answer different questions and are easy to confuse:

- `directory` — **where the `.cpp` files I want to modify live.** This tool's
  own scan scope.
- `include_dirs` — **where clang should look to resolve `#include`.** Exactly
  the compiler's `-I`. Affects parsing only; never selects a file for
  injection.

You need `include_dirs` when an `#include` is written relative to a project
include root rather than to the source file itself. The two fixture trees
under `test/` exist to show exactly this contrast.

**Interface next to the sources — `include_dirs` NOT needed** (`test/src`):

```
test/src/strategy/IStrategy.h            base class
test/src/strategy/StrategyEngine.cpp  ->  #include "StrategyEngine.h"
test/src/strategy/StrategyEngine.h    ->  #include "IStrategy.h"          same folder
test/src/strategy/alpha/AlphaStrategy.h -> #include "../StrategyEngine.h" relative
```

Every `#include` is relative to its own file, so clang resolves the whole
chain unaided. See `config_base_class_example.json` — no `include_dirs`.

**Interface in a separate include root — `include_dirs` REQUIRED**
(`test/proj`):

```
test/proj/include/framework/IExecutor.h        base class, outside the scan tree
test/proj/src/exec/OrderExecutor.h          ->  #include "framework/IExecutor.h"
test/proj/src/exec/fast/FastExecutor.h      ->  #include "../OrderExecutor.h"
```

`directory` is `test/proj/src`, but `IExecutor` lives under
`test/proj/include` and is included by include-root-relative path, so
`include_dirs` must list `test/proj/include`. See
`config_base_class_includedirs_example.json`.

Omit it and the failure is total but loud — clang cannot resolve
`IExecutor`, so `OrderExecutor` looks like it has no base class and the rule
matches nothing:

```
⚙️ Processing: test\proj\src\exec\OrderExecutor.cpp
   ⚠️  Parse error: 'framework/IExecutor.h' file not found
   ⚠️  Base-class matching may be incomplete — check "include_dirs" in the config.
Trace Injected : 0
```

`base_class` depends on this far more than the other filters do: matching by
function name needs no type information, matching by inheritance needs the
base class declaration to actually parse. That is why clang's diagnostics are
echoed to the log whenever a `base_class` rule is active — treat the warning
as "results are probably incomplete", not as noise.

Only **fatal** diagnostics are echoed, which in practice means an `#include`
clang could not resolve — precisely the failure that silently empties a
`base_class` match. Ordinary semantic errors are not reported: the hierarchy
still resolves through them, and one of them is guaranteed. Injected files
do not `#include "ScopeTrace.h"` (the tool never adds it), so every rerun
over an already-injected tree yields `unknown type name 'ScopeTrace'`.
Echoing that would train you to ignore the warning that matters.

## Known limitations

- **Headers are not modified.** Only `.cpp` files are scanned and written, so
  a virtual function defined inline in a header (`void Run() override { ... }`)
  is never given a trace. This bites hardest with `base_class`, since
  subclass overrides are often one-liners in headers. Such definitions are
  recognised during parsing and deliberately skipped — placing them by their
  header line number into the `.cpp` would land the trace in an unrelated
  function.
- **The `ScopeTrace` include is not added.** Injected files reference
  `ScopeTrace` without including its header, so they will not compile until
  you add it (a project-wide precompiled header is the usual answer).

## Examples

| File | Shows |
|---|---|
| `config_inject_example.json` | inject with a function-level `exclude` |
| `config_remove_example.json` | remove with a function-level `exclude` |
| `config_base_class_example.json` | every `Run()` override under `IStrategy`, no `include_dirs` needed |
| `config_base_class_includedirs_example.json` | every `Execute()` override under `IExecutor`, `include_dirs` required |
| `config_base_class_remove_example.json` | the exact undo of the one above — same fields, `inject` swapped for `remove` |
| `config_payloads_example.json` | a custom payload alongside the built-in one |
| `config_param_check_example.json` | a payload that names the parameters it was handed |

## Tests

Change anything, then run this. Exit code 0 means nothing that used to work
is broken.

```
python test/run_tests.py
```

No arguments and no environment setup — it locates libclang itself and puts
the fixture trees back exactly as it found them. Three parts:

**1. Scenarios.** Each runs a real rule against the fixture trees and
asserts the exact set of functions that received (or lost) a trace. Because
the expected sets are exact, the classes that must NOT match are asserted by
their absence — `NetworkMgr::Run` (same method name, unrelated class) and
`LocalCache::Execute` (same method name, no base class). Three of them run the
shipped example configs for real rather than a copy of their rules.

**2. Self checks.** Breaks the tool on purpose ten ways — degrade targeted
remove to the whole-file scan, stop restricting definitions to the main file,
widen the parse warning past fatal, drop the pre-marker fallback, go blind to
markers, ignore a rule's payload list, leave placeholders unsubstituted, stop
seeing the region already in a body, let parameter payloads into functions
whose parameters cannot be named, typo a `base_class` in an example config — and confirms the right scenarios go red
and the others stay green. A green suite only means something if it can go
red; this is what stops an assertion from quietly becoming vacuous. Skipped
when part 1 is already failing, since it asserts *which* scenarios fail.

**3. Fixture audit.** The fixtures must be trace-free before the run and
byte-identical to the snapshot after it, so no result is measuring debris
left by the previous run.

Inject scenarios:

- interface beside the sources, `include_dirs` omitted → matches
- interface in a separate include root, `include_dirs` given → matches
- same, `include_dirs` omitted → warns and injects nothing
- `base_class` matches the base class's own implementation (is-a)
- `base_class` with an empty `function` → every method in the hierarchy
- labels stay fully qualified with no `base_class` filter in play
- free functions: namespace qualified, bare at file scope

Remove scenarios (each injects first, then removes, and asserts how many
traces are left behind):

- unfiltered rule strips the whole file, unnamed
- `function` only → every `Run()`, nothing else
- `base_class` → the overrides only, `LocalCache::Execute` survives
- `base_class` with `include_dirs` missing → warns, removes nothing
- function-level `exclude` → everything except the excluded `Run()`s
- the two `base_class` example configs round-trip to zero traces
- a header-inline definition is not placed by its header line number into
  the `.cpp` (`test/inline_hdr`, built so going wrong is visible)

Marker scenarios (`test/legacy`, whose starting content each scenario writes
for itself since no rule can produce it):

- a pre-marker five-line trace is still removed, targeted and unfiltered
- `inject` does not stack a second trace on a pre-marker one
- a marked line whose payload text the tool knows nothing about is still
  removed — the assertion that removal follows the marker, not the text

Payload scenarios:

- two payloads land in the order listed, with `{indent}` and every other
  placeholder resolved — asserted against the exact bytes written
- a rerun adds only the payload that was missing
- a line that no longer matches its template is re-rendered, one beside it
  that the rule does not own is not, and an up-to-date region is left
  byte-identical
- `remove` naming one payload leaves the other, and its blank separator, alone
- `remove` naming none reaches a marker whose payload the config no longer
  defines; `remove` naming some spares it

Parameter scenarios (`test/params`, one method per shape a parameter payload
has to cope with — several named parameters, one unnamed, none, variadic):

- every parameter placeholder resolved, asserted against the exact bytes
- the unnamed and the variadic method are each skipped with a warning naming
  the reason; the one taking nothing is skipped silently under
  `requires_parameters`, and the log does not mention it at all
- without `requires_parameters`, that same method renders a count of `0`
  instead — the flag is what skips, not the placeholder
- a payload naming no parameter goes into all four, so the refusals are about
  the payload and not about the function
- a parameter payload comes back out by its marker like any other

Plus two config guards: every shipped `config_*example*.json` still passes
validation, and five malformed `payloads` configs are still rejected. Both
failures are silent ones — an undefined payload injects nothing and reports
"no changes required".

To add a scenario, append to `SCENARIOS`; the accepted keys are documented
just above the list. If a change of yours makes an existing scenario fail,
read the diff it prints before editing the expectation — that diff is the
whole point of the file.

Autodetection covers site-packages and the usual LLVM install dirs. If
libclang lives somewhere else, point at it explicitly:

```
TRACE_INJECTOR_LIBCLANG=C:/Python/Lib/site-packages/clang/native/libclang.dll \
    python test/run_tests.py
```
