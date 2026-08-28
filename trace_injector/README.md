# Trace Injector

Inserts (or strips) instrumentation at the top of C++ function bodies, driven
by `config.json` — a `ScopeTrace` guard, a parameter check, or both, chosen per
rule via `inject_type`. Function boundaries come from libclang's AST, not from
regex, so overloads and multi-line signatures are handled correctly.

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

## Config

Top level holds exactly one of `inject` or `remove` (never both), plus the
optional `exclude`, `include_dirs` and `headers` keys.

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

The four filters are ANDed together. An empty (or absent) field means "no
restriction on this dimension". Both modes accept all four: whatever an
`inject` rule can put in, the same rule under `remove` takes back out.

| Field | Meaning | Empty means |
|---|---|---|
| `directory` | Root to scan for `.cpp` files, recursively | current directory |
| `file` | Only `.cpp` files with this exact name | every `.cpp` found |
| `function` | Only functions with this exact name | every function |
| `base_class` | Only methods of a class that IS this class or derives from it, at any depth | no hierarchy filter |
| `inject_type` | *Not* a filter — **what** to insert. `inject` only | `["trace"]` |

### `inject_type`

Which blocks to write into each matched function. Per rule, so different
directories can get different treatment:

```json
"inject": [
    { "directory": "src",       "function": "", "inject_type": ["trace"] },
    { "directory": "src/hot",   "function": "", "inject_type": ["trace", "validate"] }
]
```

| Value | Writes |
|---|---|
| `trace` | the `ScopeTrace` guard |
| `validate` | a `__param_names[]` table and a `validate_params(...)` call |

```cpp
static const char* __param_names[] = { "account_id", "notional", "max_notional" };
validate_params("RiskChecker::CheckLimits", __param_names, account_id, notional, max_notional);
```

Two cases where fewer parameters come out than went in:

- **No parameters at all** → no block. There is nothing to check, and
  `const char* __param_names[] = {}` does not compile. So a rule can name
  `validate` and legitimately produce no validate blocks whatsoever; check the
  log rather than assuming.
- **A parameter with no name** (`void Snapshot(int account_id, double* out, int)`)
  → skipped, and the rest of the block is written as normal. An unnamed
  parameter cannot be referred to, so there is nothing to pass; the table and
  the argument list stay consistent with each other, just shorter than the
  signature.

Overloads are handled per definition, not per name: two overloads with
different parameter lists each get their own.

`remove` rules do **not** take `inject_type`. See below for why.

### `headers`

`validate` calls `validate_params()`, which lives in a **generated**
`ParameterCheck.h` — generated against one specific `Types.h`, because the
checks it performs depend on the types it is checking. So a rule asking for
`validate` has to say where that `Types.h` is:

```json
"headers": {
    "types_header": "test/include/Types.h",
    "generate_into": "test/include"
}
```

| Key | Meaning | Empty means |
|---|---|---|
| `types_header` | the project's `Types.h`. **Required** by any `validate` rule | refuse to run |
| `generate_into` | where to write the generated `ParameterCheck.h` | next to `Types.h` |

Generating it is the **first** action of the run, before a single `.cpp` is
opened, and the generator's verdict on `Types.h` decides whether the run
happens at all:

```
⚙️ Generating ParameterCheck.h from: test\include\TypesUnprepared.h
   --> Validating test\include\TypesUnprepared.h...
   [Validation Failed] Enum 'Side' lacks 'check_traits<Side>' specialization.
   [Build Stopped] Types validation failed. Generation aborted.
   ❌ Types.h was rejected, so validate_params() would not compile against it.
   ❌ Nothing was injected. Fix the types, or drop "validate" from the rule.
```

Exit code 1, and **nothing was modified** — not the sources, not the
generated headers. That is worth more than it looks: an injection that cannot
compile is worse than no injection, and undoing one costs a second run over
the whole tree. The generator writes nothing when it rejects a `Types.h`, and
this aborts before its first write, so the two halves compose into "a refused
run leaves everything exactly as it found it".

The generator is the sibling `parameters_check` tool, used as a library and
found next to this one. It needs `jinja2` — the only dependency on this path,
and only on this path.

Neither key means anything to a `remove` run, or to a `trace`-only inject.
Neither has any use for a `Types.h`, so neither is asked for one.

Keys `headers` does not read are rejected rather than ignored. A previous
version of this tool shipped configs carrying a `headers` key that nothing
read, which reads like a feature until you depend on it.

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

### What `remove` removes

**A remove rule says where to clean, never what.** It has no `inject_type`, and
that is deliberate: whatever the injector left at the top of a matched
function comes out — trace, validate, both — and the function is left
byte-identical to how it started.

Being selective was a bug, not a feature. A remove that understood only
`ScopeTrace` left the validate block of a `["trace", "validate"]` injection
sitting in place. Nothing then reported the file as dirty, so the next `inject`
saw no trace, wrote a fresh block above the orphan, and the file ended up with
two `__param_names` declarations in one scope and no longer compiled.

Beyond that, `remove` mirrors `inject`, with one deliberate asymmetry — the
filters decide the *scope*, and their presence also decides *how* the file is
read:

- **Any filter present** (`function`, `base_class`, or a matching `exclude`)
  → the file is parsed and only the blocks sitting at the top of the selected
  functions are deleted. Same selection pass as `inject`, so the same rule
  takes back out exactly what it put in, and the log names each function it
  removed from. Note this means adding a single `exclude` entry switches an
  otherwise unfiltered `remove` onto the parsing path.
- **No filter at all** → no parsing, just a line scan that strips *every*
  injected block in the matched files. Blunter, but it also catches blocks the
  injector never placed (hand-written, or left over from a rule you have since
  edited) and blocks in files clang cannot parse. The log names the kinds it
  found instead of the function, since there is no AST to ask:

```
⚙️ Processing: test\src\OrderMgr.cpp
   ✨ Removed injection [trace, validate]
   ✨ Removed injection [trace]
```

Adding a new injection kind does not require touching `remove`. Each kind
declares its own line markers in `INJECTION_KINDS` (`constants.py`) alongside
the code that writes it, and `remove` matches on those — so the two halves
cannot drift apart.

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

- **Headers are not scanned.** Only `.cpp` files, so a virtual function
  defined inline in a header (`void Run() override { ... }`) is never
  touched. This bites hardest with `base_class`, since subclass overrides
  are often one-liners in headers.
- **No `#include` is added.** Injected files reference `ScopeTrace` and
  `validate_params` without including their headers, so they will not compile
  until you add them (a project-wide precompiled header is the usual answer).
  `headers` closes half of this: it makes sure `ParameterCheck.h` exists and
  was generated for your `Types.h`. Getting each `.cpp` to *find* it is still
  yours to arrange. `inject_files_examples/` holds the header side of the
  bargain — what `ScopeTrace` is, and what it needs from your logger.

## Examples

| File | Shows |
|---|---|
| `config_inject_example.json` | inject with a function-level `exclude` |
| `config_remove_example.json` | remove with a function-level `exclude` |
| `config_base_class_example.json` | every `Run()` override under `IStrategy`, no `include_dirs` needed |
| `config_base_class_includedirs_example.json` | every `Execute()` override under `IExecutor`, `include_dirs` required |
| `config_base_class_remove_example.json` | the exact undo of the one above — same fields, `inject` swapped for `remove` |
| `config_inject_types_example.json` | two directories, a different `inject_type` for each, plus the `headers` block the `validate` one needs |
| `config_inject_types_remove_example.json` | the undo of the one above — one unfiltered rule per tree, no `inject_type` needed |

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
`LocalCache::Execute` (same method name, no base class). Two of them run the
shipped example configs for real rather than a copy of their rules.

**2. Self checks.** Breaks the tool on purpose five ways — degrade targeted
remove to the whole-file scan, make remove blind to everything but `trace`,
pass one argument fewer than the name table names, widen the parse warning past
fatal, typo a `base_class` in an example config — and confirms the right
scenarios go red and the others stay green. A green suite only means something
if it can go red; this is what stops an assertion from quietly becoming vacuous.
Skipped when part 1 is already failing, since it asserts *which* scenarios fail.

**3. Fixture audit.** The fixtures must carry no injected code of any kind
before the run and be byte-identical to the snapshot after it, so no result is
measuring debris left by the previous run.

Three checks sit ahead of the scenarios, since they decide whether a run
happens at all: the `headers` block accepts the keys it reads and rejects the
ones it does not, the pre-flight generates both headers for a `Types.h` it
accepts and neither for one it rejects, and — end to end through the CLI, which
is the only way to reach the pre-flight — a rejected `Types.h` exits non-zero
with the fixture trees byte-identical. `test/include/Types.h` and
`TypesUnprepared.h` are that pair; the accepted run goes first and has to
change something, or "modified nothing" would pass for a rule that matched
nothing. These are the only checks here that need `jinja2`, and they skip
rather than fail without it.

Inject scenarios:

- interface beside the sources, `include_dirs` omitted → matches
- interface in a separate include root, `include_dirs` given → matches
- same, `include_dirs` omitted → warns and injects nothing
- `base_class` matches the base class's own implementation (is-a)
- `base_class` with an empty `function` → every method in the hierarchy
- labels stay fully qualified with no `base_class` filter in play
- free functions: namespace qualified, bare at file scope
- `validate` names match the arguments at every arity

That last one is the only scenario that reads the injected code instead of
counting it: for every validate block in the fixtures, the quoted names and the
arguments passed have to be the same identifiers in the same order. Counts
cannot see that distinction, which is why `test/src/risk/RiskChecker.cpp` exists
— three- and four-parameter methods, an overload pair whose two definitions
must not share a parameter list, a parameter with no name, and one method with
no parameters at all.

Remove scenarios (each injects first, then removes, and asserts how many
blocks are left behind — counted per kind, so validate debris a trace count
walks past still fails the assertion):

- unfiltered rule strips the whole file, unnamed
- unfiltered rule strips `validate` as well as `trace`
- targeted rule strips `validate` as well as `trace`
- `function` only → every `Run()`, nothing else
- `base_class` → the overrides only, `LocalCache::Execute` survives
- `base_class` with `include_dirs` missing → warns, removes nothing
- function-level `exclude` → everything except the excluded `Run()`s
- the two `base_class` example configs round-trip to zero traces
- the two `inject_types` example configs clean both fixture trees

Round trips assert byte equality rather than counts, in both directions:

```
inject -> remove            == the original file, byte for byte
inject -> remove -> inject  == what the first inject produced
```

The second is the one that earns its keep. A remove that leaves one block of a
two-block injection behind passes every count-based check; only re-injecting
and comparing catches the duplicate it causes.

Plus a guard that every shipped `config_*example*.json` still passes
validation.

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
