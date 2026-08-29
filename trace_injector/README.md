# Trace Injector

Inserts (or strips) instrumentation in C++ function bodies, driven by
`config.json` — a `ScopeTrace` guard, a parameter check, a `try`/`catch` around
the body, or any combination, chosen per rule via `inject_type`. Function
boundaries come from libclang's AST, not from regex, so overloads and multi-line
signatures are handled correctly.

```
pip install libclang
python trace_injector.py --config config.json
```

That is the whole install. The tool locates the shared library itself, because
the clang bindings load it through the OS loader and the OS loader does not look
inside site-packages — so `pip install libclang` alone puts the file on disk and
the import still fails. The path it settled on is logged whenever it had to go
looking, since "which libclang answered" is the first thing worth knowing when a
`base_class` rule matches nothing:

```
Trace Injector v1.2
Mode: inject
libclang: C:\Python\Lib\site-packages\clang\native\libclang.dll
```

If yours lives somewhere the search does not cover, name it and the search is
skipped entirely:

```
TRACE_INJECTOR_LIBCLANG=/opt/llvm/lib/libclang.so python trace_injector.py --config config.json
```

Log lines name each function by its fully qualified name, so overrides that
share a method name stay distinguishable, and end with the kinds actually
written into it:

```
✨ Injected: StrategyEngine::Run() [trace]
✨ Injected: AlphaStrategy::Run() [trace]
✨ Injected: util::Reset() [trace]              free function, namespace only
✨ Injected: Normalize() [trace, validate]      free function at file scope
```

## Config

Top level holds exactly one of `inject` or `remove` (never both), plus the
optional `exclude` and `include_dirs` keys. A top-level key that is none of
those four is an error rather than something ignored — a key nothing reads
looks like a feature until you depend on it.

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

| Field         | Meaning                                                                     | Empty means         |
| ------------- | --------------------------------------------------------------------------- | ------------------- |
| `directory`   | Root to scan for `.cpp` files, recursively                                  | current directory   |
| `file`        | Only `.cpp` files with this exact name                                      | every `.cpp` found  |
| `function`    | Only functions with this exact name                                         | every function      |
| `base_class`  | Only methods of a class that IS this class or derives from it, at any depth | no hierarchy filter |
| `inject_type` | *Not* a filter — **what** to insert. `inject` only                          | `["trace"]`         |

### `inject_type`

Which blocks to write into each matched function. Per rule, so different
directories can get different treatment:

```json
"inject": [
    { "directory": "src",       "function": "", "inject_type": ["trace"] },
    { "directory": "src/hot",   "function": "", "inject_type": ["trace", "validate"] }
]
```

| Value      | Writes                                                      |
| ---------- | ----------------------------------------------------------- |
| `trace`    | the `ScopeTrace` guard                                      |
| `validate` | a `__param_names[]` table and a `validate_params(...)` call |
| `guard`    | a `try` / `catch` around the body, reporting what it caught |

#### `validate`

```cpp
static const char* __param_names[] = { "account_id", "notional", "max_notional" };
validate_params("RiskChecker::CheckLimits", __param_names, account_id, notional, max_notional);
```

Two cases where fewer parameters come out than went in:

- **No parameters at all** → no block. There is nothing to check, and
  `const char* __param_names[] = {}` does not compile.
- **A parameter with no name** (`void Snapshot(int account_id, double* out, int)`)
  → skipped, and the rest of the block is written as normal. An unnamed
  parameter cannot be referred to, so there is nothing to pass; the table and
  the argument list stay consistent with each other, just shorter than the
  signature.

**Expect most functions to get no validate block.** `void Run()`, `Stop()`,
`OnTick()` — the no-argument methods that make up the bulk of most code — take
nothing, so they get a trace and nothing else. A `["trace", "validate"]` rule
producing validate blocks in three files out of eight is the normal result, not
a broken one. The log says which kinds each function got, so read it rather than
grepping the tree and guessing:

```
⚙️ Processing: test\src\OrderMgr.cpp
   ✨ Injected: OrderMgr::SubmitOrder() [trace, validate]
   ✨ Injected: OrderMgr::OnConnected() [trace]
   ✨ Added include: ScopeTrace.h
   ✨ Added include: ParameterCheck.h

⚙️ Processing: test\src\market\MarketData.cpp
   ✨ Injected: MarketData::OnTick() [trace]
   ✨ Added include: ScopeTrace.h
```

`MarketData.cpp` has no `ParameterCheck.h` because nothing in it needed one.

Overloads are handled per definition, not per name: two overloads with
different parameter lists each get their own — so `RiskChecker::Margin` appears
twice in the log, once per definition.

#### `guard`

The one kind that does not just prepend a block. It wraps the body it found,
leaving the code between the braces exactly as it was:

```cpp
bool OrderMgr::SubmitOrder(
    int order_id
)
{
    try  // inject automatically: guard
    {  // inject automatically: guard

    return true;
    }  // inject automatically: end of guard
    catch (const std::exception& error)  // inject automatically: end of guard
    {  // inject automatically: end of guard
        ErrorLogger::LogError("OrderMgr", "SubmitOrder", "std::exception", error.what());  // inject automatically: end of guard
        throw;  // inject automatically: end of guard
    }  // inject automatically: end of guard
    catch (...)  // inject automatically: end of guard
    {  // inject automatically: end of guard
        ErrorLogger::LogError("OrderMgr", "SubmitOrder", "unknown", "unrecognised exception");  // inject automatically: end of guard
        throw;  // inject automatically: end of guard
    }  // inject automatically: end of guard
}
```

Four things about that are deliberate:

- **`throw;`, always.** The guard reports the error and rethrows it. Swallowing
  would change what your program does, and in a function that returns something
  it would run off the end of the body without returning — undefined behaviour,
  not a compile error. If you want the exception stopped, stop it yourself; this
  tool does not make that decision for you.
- **The body is not reindented.** It is now one level deeper than it looks. That
  is the price of this tool's actual promise: `remove` gives you back the file
  you had, byte for byte, and reindenting would turn every injection into a diff
  across the whole function.
- **Two arms, so nothing gets past it.** `catch (...)` reports what
  `std::exception` cannot describe. Whatever error code the exception carries is
  reachable through `error.what()`.
- **It goes innermost.** With `["trace", "validate", "guard"]`, the `try` opens
  *below* the trace object and the parameter check, so the `ScopeTrace` is still
  alive while the catch runs and its destructor logs the exit afterwards.

A body written entirely on its opening line — `int size() const { return n_; }` —
is skipped and says so, because there is no line between the braces to wrap and
guessing would mean writing a `}` into the middle of a statement.

`remove` rules do **not** take `inject_type`. See below for why.

### The `#include` it adds

Injected code names `ScopeTrace`, `validate_params` and `ErrorLogger`, so the
file it lands in has to include the header each of those lives in. The tool adds
it:

```cpp
#include "RiskChecker.h"
#include "ScopeTrace.h"  // inject automatically: include for trace
#include "ParameterCheck.h"  // inject automatically: include for validate
#include "ErrorLogger.h"  // inject automatically: include for guard
```

There is no config key for this and no path in it. The headers are named the
way your own sources name their own headers, and they resolve the same way —
through your build's `-I`. Nothing here goes looking for them on disk.

| Kind       | Header             | Lives in                                    |
| ---------- | ------------------ | ------------------------------------------- |
| `trace`    | `ScopeTrace.h`     | the sibling `util` repo, `ScopeTrace/`      |
| `validate` | `ParameterCheck.h` | the sibling `util` repo, `Parameter_Check/` |
| `guard`    | `ErrorLogger.h`    | the sibling `util` repo, at the top         |

The `try`/`catch` a `guard` writes needs no header of its own — but its catch
arms have to report the error *somewhere*, and `ErrorLogger::LogError` is where
this project reports errors. Reporting nothing at all was the alternative, and a
guard that silently rethrows is not worth injecting. If your tree reaches
`ErrorLogger` some other way, or you want a different reporter, that is the
`header` field of the `guard` entry in `INJECTION_KINDS` and the two lines above
it.

`ParameterCheck.h` is yours to prepare before the first `validate` run — it and
the `CheckTraits.h` / `Types.h` it includes are hand-maintained, and this tool
neither generates nor validates them. An earlier version generated
`ParameterCheck.h` from a `Types.h` named in a `headers` config block; that is
gone, and so is the block.

Three rules govern the include, and each one is a bug that has to be prevented
rather than a nicety:

- **It follows what was written, never what the rule asked for.** A `validate`
  rule meeting a function with no parameters writes no block, so it gets no
  `ParameterCheck.h` — otherwise the rule would drag `Types.h` into translation
  units that have no use for it.
- **It goes after the file's last unconditional `#include`.** Last, so it lands
  below the file's own header. Unconditional, because the final `#include` in a
  real file is often inside `#if defined(_WIN32)`, and appending there would
  make a header the injected code always needs depend on the platform.
- **It survives a partial remove.** The include is file-scoped while the blocks
  are function-scoped, so `remove` only deletes it once the last block of its
  kind is gone from that file. A rule naming one function out of five leaves it
  in place for the other four.

An include already in the file is left alone — a second copy would compile, but
then `remove` would have to guess which of the two is safe to delete. And an
include with no marker comment on it is not this tool's, and is never touched.

Both directions are logged per file and counted in the summary, so "which of my
files just grew a dependency on `Types.h`" is answerable from the log:

```
⚙️ Processing: test\src\risk\RiskChecker.cpp
   ✨ Injected: RiskChecker::CheckOrder()
   ✨ Added include: ScopeTrace.h
   ✨ Added include: ParameterCheck.h

Includes Added : 11
Includes Gone  : 0
```

### `base_class`

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

**Only what this tool wrote.** Every line it injects carries a marker comment
naming the kind that wrote it:

```cpp
    ScopeTrace trace(  // inject automatically: trace
```

That comment is the whole of what `remove` looks for. It does not recognise
`ScopeTrace` or `validate_params` as C++ — so your own hand-written guard, even
one spelled exactly like the injected version, is not this tool's to delete.

> **Upgrading:** blocks written by a version of this tool that predates the
> marker carry no comment, and the current `remove` cannot see them. Strip them
> with the old version first, or delete them by hand.

**A remove rule says where to clean, never what.** It has no `inject_type`, and
that is deliberate: whatever the injector left in a matched function comes out —
trace, validate, both halves of a guard, all of it — and the function is left
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
  → the file is parsed and only the marked lines inside the selected functions
  are deleted — the whole body is searched, not just the top of it, because a
  `guard` leaves its catch arms just above the function's own brace. Same
  selection pass as `inject`, so the same rule takes back out exactly what it put
  in, and the log names each function it removed from. Note this means adding a
  single `exclude` entry switches an otherwise unfiltered `remove` onto the
  parsing path.
- **No filter at all** → no parsing, just a line scan that strips *every*
  marked block in the matched files. Blunter, but it also catches blocks left
  over from a rule you have since edited, and blocks in files clang cannot
  parse. The log names the kinds it found instead of the function, since there
  is no AST to ask:

```
⚙️ Processing: test\src\OrderMgr.cpp
   ✨ Removed injection [trace, validate]
   ✨ Removed injection [trace]
```

Counted per injection, not per marked run: a `guard` writes at both ends of a
function, and the run of catch arms is the bottom of an injection already
counted. So the number the summary reports for a remove is the number a matching
inject reported, on either path.

Adding a new injection kind does not require touching `remove`, or the include
handling either. A kind is one entry in `INJECTION_KINDS` (`constants.py`) — its
name, the function that writes it, the header it needs — and everything else
reads that entry: the markers are derived from the name, so the two halves cannot
drift apart. The writer returns two lists, what goes above the body and what goes
below it; a kind that only prepends returns nothing for the second.

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
still resolves through them, so echoing them would train you to ignore the
warning that matters.

One fatal is filtered out all the same: this tool's own header. Rerun over an
already-injected tree without an `-I` covering `ScopeTrace.h` and clang says
`'ScopeTrace.h' file not found` for every single file, which tells you nothing
about base-class matching — the injected include sits *below* the file's own, so
everything the hierarchy needs has already been read by the time clang gets
there. A header of *yours* that cannot be found is still reported, and still
reported first, because it is higher up the file.

## Known limitations

- **Headers are not scanned.** Only `.cpp` files, so a virtual function
  defined inline in a header (`void Run() override { ... }`) is never
  touched. This bites hardest with `base_class`, since subclass overrides
  are often one-liners in headers.
- **The headers have to be reachable.** The tool writes the `#include`; making
  the name resolve is your build's job, the same `-I` your own headers already
  rely on. None of the three ships here — they all live in the sibling `util`
  repo, and `ScopeTrace.h` needs the `Logger.h` next to it. Nothing is checked
  before the sweep: a `validate` run against a `ParameterCheck.h` you have not
  prepared injects happily and fails at compile time.
- **A `guard` cannot wrap a constructor's initialiser list.** A `try` covering
  member initialisation is a *function-try-block* — `Foo::Foo() try : x_(f())`,
  with the `try` before the colon — and that is not the shape this writes. A
  constructor gets its body wrapped and its initialiser list left outside it,
  which is valid C++ but not what you would want if `f()` is the thing that
  throws.
- **A `guard` does not reindent the body.** By design; see above.

## Examples

All under `configs_examples/`:

| File                                         | Shows                                                                                                                  |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `config_inject_example.json`                 | inject with a function-level `exclude`                                                                                 |
| `config_remove_example.json`                 | remove with a function-level `exclude`                                                                                 |
| `config_base_class_example.json`             | every `Run()` override under `IStrategy`, no `include_dirs` needed                                                     |
| `config_base_class_includedirs_example.json` | every `Execute()` override under `IExecutor`, `include_dirs` required                                                  |
| `config_base_class_remove_example.json`      | the exact undo of the one above — same fields, `inject` swapped for `remove`                                           |
| `config_inject_types_example.json`           | two directories, a different `inject_type` for each — so one tree gets both includes and the other only `ScopeTrace.h` |
| `config_inject_types_remove_example.json`    | the undo of the one above — one unfiltered rule per tree, no `inject_type` needed                                      |
| `config_guard_example.json`                  | all three kinds over one tree, `guard` alone over another                                                              |
| `config_guard_remove_example.json`           | the undo of the one above                                                                                              |

## Tests

Change anything, then run this. Exit code 0 means nothing that used to work
is broken.

```
python test/run_tests.py
```

No arguments and no environment setup — it finds libclang through the tool's own
locator, not a copy of it, and puts the fixture trees back exactly as it found
them. Three parts:

**1. Scenarios.** Each runs a real rule against the fixture trees and
asserts the exact set of functions that received (or lost) a trace. Because
the expected sets are exact, the classes that must NOT match are asserted by
their absence — `NetworkMgr::Run` (same method name, unrelated class) and
`LocalCache::Execute` (same method name, no base class). Two of them run the
shipped example configs for real rather than a copy of their rules.

Every scenario also carries two invariants it did not have to ask for: per file,
the injected `#include` is present exactly when there is injected code needing it
and never twice, and every fixture has as many `{` as `}`. The first turns each
inject scenario into a check that the include was added and each remove scenario
into a check that it was taken away — without any scenario hard-coding a count.
Both ways of getting that wrong are quiet: a missing include is a file that does
not compile, and a leftover one drags `Types.h` into a translation unit with no
use for it. The brace count is there because `guard` is the first kind that writes
below the body as well as above it, so it is the first that can leave a file with
an unmatched brace — a whole category of breakage no marker count would see.

**2. Self checks.** Breaks the tool on purpose eleven ways — degrade targeted
remove to the whole-file scan, make remove blind to everything but `trace`, pass
one argument fewer than the name table names, claim every kind the rule asked for
whether or not it wrote anything, inject blocks without their include, leave the
include behind after the last block went, report the tool's own header as a parse
problem, open a `guard`'s `try` and never close it, drop the `throw;` from its
catch arms, look only at the top of the body when removing, typo a `base_class` in
an example config — and confirms the right scenarios go red and the others stay
green. A green suite only means something if
it can go red; this is what stops an assertion from quietly becoming vacuous.
Skipped when part 1 is already failing, since it asserts *which* scenarios fail.

The claim-every-kind one changes no file at all: counts, byte equality, both
round trips stay green. What goes red is the log — which functions it says got a
validate block — and the include, since both are meant to follow *what was
written* rather than what was asked for. That the two fail together is the point.

The three `guard` breakages are graded, and what each one is invisible to is the
finding. An unclosed `try` still counts, removes and round-trips perfectly — only
the brace check refuses it. A guard with no `throw;` passes even that: right size,
right place, right include, restores byte for byte, and every exception in the
program now stops where it was thrown. Only reading the emitted C++ back notices.
And a targeted remove that looks only at the top of the body — which was correct
code until a kind wrapped a body — leaves the catch arms behind while reporting
success, so it goes red on the guard scenarios and stays green on every
`trace`/`validate` one.

The two include breakages are opposites, and their `must_pass` lists are where
the rule actually gets pinned down. Never adding the include leaves *"warns and
injects nothing"* green, because a rule that wrote nothing needs nothing. Never
removing it leaves *"`function` only → every `Run()`"* green — every file holding
a `Run` holds something else too, so none of them may drop its include — while
*"function-level `exclude`"* goes red, because the files with no `Run` in them
did lose their last block.

**3. Fixture audit.** The fixtures must carry no injected code of any kind
before the run and be byte-identical to the snapshot after it, so no result is
measuring debris left by the previous run.

Three checks sit outside the scenario list:

- **A top-level config key nothing reads is rejected**, including the `headers`
  block this tool used to ship. Silence there would read as "your
  `ParameterCheck.h` is being generated" long after that stopped being true.
- **Hand-written code that says `ScopeTrace` survives a remove**, and an include
  the file already had is not duplicated. Nothing else here could notice: every
  other check reads `ScopeTrace trace(` as proof of an injection, so a remove
  that deleted somebody's own guard would look like a job well done.
- **End to end through the CLI**, inject then remove then byte-identical again.
  Everything else calls `process_rule` directly and never reaches `cli.py`, so a
  config the CLI chokes on — or a summary line naming a stat nobody counts —
  would stay hidden until someone ran the tool for real. The inject half has to
  change something, or "restored" would pass for a run that did nothing.

Inject scenarios:

- interface beside the sources, `include_dirs` omitted → matches
- interface in a separate include root, `include_dirs` given → matches
- same, `include_dirs` omitted → warns and injects nothing
- `base_class` matches the base class's own implementation (is-a)
- `base_class` with an empty `function` → every method in the hierarchy
- labels stay fully qualified with no `base_class` filter in play
- free functions: namespace qualified, bare at file scope
- `validate` names match the arguments at every arity
- `guard` wraps every body: both arms, both rethrows, closing at the bottom
- all three kinds in one function, in the order that has to hold

The last two are the only scenarios that read the injected code instead of
counting it. For every validate block in the fixtures, the quoted names and the
arguments passed have to be the same identifiers in the same order. Counts
cannot see that distinction, which is why `test/src/risk/RiskChecker.cpp` exists
— three- and four-parameter methods, an overload pair whose two definitions
must not share a parameter list, a parameter with no name, and one method with
no parameters at all.

Every guard is read back the same way: two catch arms, both rethrowing, both
naming the function they were written into, and the whole thing sitting directly
above that function's closing brace. Every `try` written has to have a matching
set of arms, so half a guard is reported rather than counted. The placement matters
as much as the shape — arms inserted anywhere else in the body leave the braces
balanced and the file compiling, with everything after them quietly unguarded.

The validate scenario also pins down the mapping the log reports: `trace` for all
21 functions, `validate` for exactly the 8 that take parameters. Asserted against
the log rather than the files, because the log is what a reader judges the run by —
and with 13 of 21 taking no arguments, "validate did nothing" is what a *correct*
run looks like unless the log says otherwise. A `guard` sweep is the opposite case:
every function is wrapped, and nothing anywhere gets a `ScopeTrace`.

Remove scenarios (each injects first, then removes, and asserts how many
blocks are left behind — counted per kind, so validate debris a trace count
walks past still fails the assertion):

- unfiltered rule strips the whole file, unnamed
- unfiltered rule strips `validate` as well as `trace`
- targeted rule strips `validate` as well as `trace`
- unfiltered rule strips both halves of a `guard`, counting each guard once
- targeted rule strips both halves of a `guard`
- `function` only → every `Run()`, nothing else
- `base_class` → the overrides only, `LocalCache::Execute` survives
- `base_class` with `include_dirs` missing → warns, removes nothing
- function-level `exclude` → everything except the excluded `Run()`s
- the two `base_class` example configs round-trip to zero traces
- the two `inject_types` example configs clean both fixture trees
- the two `guard` example configs clean both fixture trees

The `guard` removes assert what the setup planted before the remove runs. A remove
scenario claiming "nothing left" passes just as well when the inject never wrote
anything, and half a guard is exactly the kind of inject bug that would make it
pass.

Round trips assert byte equality rather than counts, in both directions:

```
inject -> remove            == the original file, byte for byte
inject -> remove -> inject  == what the first inject produced
```

The second is the one that earns its keep. A remove that leaves one block of a
two-block injection behind passes every count-based check; only re-injecting
and comparing catches the duplicate it causes.

Byte equality says the most about `guard`, the one kind that does not simply
prepend: it proves the closing half went in above the function's own brace and
came back out without taking a line of the body with it. Eight trips are run:
trace only, trace + validate, guard only, all three at once, two of those targeted
both ways, and both shipped example pairs.

Plus a guard that every shipped `config_*example*.json` still passes
validation.

To add a scenario, append to `SCENARIOS`; the accepted keys are documented
just above the list. If a change of yours makes an existing scenario fail,
read the diff it prints before editing the expectation — that diff is the
whole point of the file.

`TRACE_INJECTOR_LIBCLANG` works here exactly as it does for the tool, since it
is the same locator.

## Verification & Compilation Test (`verify_compile.py`)

`verify_compile.py` is an end-to-end verification script. It applies the code injection, attempts to compile (and optionally execute) the target C++ files using `g++`, and automatically restores the Git workspace state afterwards.

### Prerequisites

- `g++` (supporting C++17) must be available in your `PATH`. 
- Windows environment requiring Winsock socket API (the script automatically links `-lws2_32`).

### Quick Start

```bash
# 1. Full compilation & binary execution (Default Mode)
python tools/verify_compile.py

# 2. Fast syntax-only validation (No linking or main.cpp required)
python tools/verify_compile.py -s

# 3. Interactive step-by-step mode (Pause after each step to inspect changes)
python tools/verify_compile.py -i

# 4. Custom config file and target source directory
python tools/verify_compile.py -c configs_examples/config_inject_example.json -d test/src
```

### Execution Modes & Features

- **Full Compilation & Execution (Default)**:
  Compiles all `.cpp` files in the target directory (e.g., `test/src`) along with implementation dependencies under `util/` (excluding standalone test mains). If `main.cpp` exists in the target directory, it builds `test_runner` and executes it directly to verify runtime `ScopeTrace` outputs.

- **Syntax Validation Mode (`-s` / `--syntax-only`)**:
  Uses `g++ -fsyntax-only` to validate syntax, include paths, and type definitions without linking or generating binaries. This mode does not require a `main.cpp`.

- **Interactive Mode (`-i` / `--interactive`)**:
  Pauses the workflow after each step (`Inject` -> `Compile` -> `Execute` -> `Cleanup`). You can open and inspect the modified C++ source files in your editor during the injection step before proceeding to compilation.

- **Automatic Cleanup**:
  Regardless of success or failure, the script executes `git checkout` in its `finally` block to guarantee no dirty or injected code is left in your working tree.
