# Configurable payloads — design

Status: agreed 2026-08-27, implementation in progress.

Today `constants.py` hardcodes one thing to insert:

```python
TRACE_LINES = [
    "    ScopeTrace trace(\n",
    ...
]
```

The goal is to make *what* gets inserted configurable, so the same targeting
machinery can also inject a parameter check built from the function's real
parameter names — and take it back out again.

## What libclang gives us

Verified, not assumed:

```
trading::Impl::OnTick
    name='tick'    type='const TradeData &'    kind=LVALUEREFERENCE
    name='window'  type='const Vec<double> &'  kind=LVALUEREFERENCE
    name='raw'     type='int *'                kind=POINTER
```

Parameter names, written types, canonical types and type kinds are all
available from `node.get_arguments()`, so
`check_all("Impl::OnTick", {"tick","window","raw"}, tick, window, raw)` can be
generated.

Two gaps found while probing:

- Constructors and destructors are `CursorKind.CONSTRUCTOR` / `DESTRUCTOR`,
  and templates are `FUNCTION_TEMPLATE`. None are in `FUNCTION_KINDS`, so
  none are ever injected today. A constructor is often the most valuable
  place to check parameters.
- **Bug, must be fixed first.** `iter_target_functions` walks the whole
  translation unit, which includes every header, but the caller indexes into
  the `.cpp`'s line array. A function defined inline in a header therefore
  gets its payload inserted at the *header's* line number inside the `.cpp`.
  Reproduced: `Widget::Run` defined on line 5 of `Widget.h` landed inside
  `Widget::Later`'s `if` block, labelled `Widget::Run`. It usually misses
  only because the brace search finds no `{` on that line — luck, not
  design. Fix: skip nodes whose `location.file` is not the file being
  rewritten.

  This blocks the payload work: a misplaced `check_all(tick, window, raw)`
  references names that do not exist in the scope it landed in.

  The README's "headers are not scanned, so inline overrides are never
  touched" is wrong as written — they are not skipped, they are mistargeted.

## Why ScopeTrace's destructor is the right call

Logging the exit from the destructor handles four things at once, not just
the early return: multiple returns, exceptions, `goto`/`break` out of the
body, and any return a future edit adds. The predecessor tool
(`utilLocal/CppLogInjector.py`) instead searched for the matching closing
brace with a regex and appended an exit log there; that cannot survive
nested braces, braces in string literals, or an early return.

A consequence worth designing around: **if `ScopeTrace` degrades to an empty
class under a compile-time flag**, injected code can stay in the source. A
release build defines the flag and everything disappears; a debug build gets
it all back. `remove` then drops from "required before shipping" to "a
convenience when you want the source clean".

That constrains payloads: every payload must depend only on things a
compile-time switch can remove. It is one of the reasons not to inject
`if (!check_all(...)) return;` — control flow cannot be switched off.

## Three layers

| Layer | Answers | Lives in |
|---|---|---|
| Payload definition | what to insert | the `payloads` table in the config |
| Rule | which functions | the existing filters, plus a `payloads` field |
| Marker | how to take it back out | a `// @tj:<name>` comment on each injected line |

`payloads` is an ordinary rule field, exactly like `function` and
`base_class`. The inject/remove symmetry already built therefore extends to
it for free: `"payloads": ["param_check"]` under `remove` strips the
parameter checks and leaves the traces alone. No new removal logic.

### Config

```json
{
    "inject": [
        {
            "directory": "src",
            "base_class": "IStrategy",
            "function": "Run",
            "payloads": ["scope_trace", "param_check"]
        }
    ],

    "payloads": {
        "scope_trace": {
            "include": "util/ScopeTrace.h",
            "lines": [
                "{indent}ScopeTrace _tj_scope(__FILE__, __LINE__, \"{qualified_name}\");"
            ]
        },

        "param_check": {
            "include": "util/ParameterCheck.h",
            "requires_parameters": true,
            "lines": [
                "{indent}check_all(\"{qualified_name}\", {param_name_list}, {param_names});"
            ]
        }
    },

    "include_dirs": ["src", "util"]
}
```

Omitting `payloads` on a rule means `["scope_trace"]`, which is today's
behaviour, so existing configs keep working unchanged. The `payloads` table
may also be a path string pointing at a shared file — payloads are
infrastructure, rules are what you edit daily.

Order in the list is insertion order. `scope_trace` first, so entry is
logged before a parameter failure is reported.

### Placeholders

| Placeholder | Expands to | Why |
|---|---|---|
| `{indent}` | the function body's actual indentation | today's hardcoded 4 spaces is wrong inside a namespace |
| `{qualified_name}` | `trading::AlphaStrategy::Run` | beats `__FUNCTION__`, which is bare on gcc and qualified on MSVC; the injector already computes it |
| `{function}` / `{class}` | bare names | |
| `{param_names}` | `tick, window, raw` | |
| `{param_name_list}` | `{"tick", "window", "raw"}` | |
| `{param_count}` | `3` | |

`requires_parameters: true` skips functions with no usable parameters rather
than emitting `check_all("f", {}, );`, which does not compile.

### Markers

```cpp
void AlphaStrategy::Run(const TradeData& tick)
{
    ScopeTrace _tj_scope(__FILE__, __LINE__, "AlphaStrategy::Run");  // @tj:scope_trace
    check_all("AlphaStrategy::Run", {"tick"}, tick);                 // @tj:param_check

    ...
}
```

Removal deletes lines carrying `@tj:<name>`. This buys:

- **Removal stops needing to know payload content.** Today it greps for the
  literal `ScopeTrace trace` and finds the block end by looking for `");"`;
  neither survives configurable payloads. The injected region becomes "the
  contiguous marked prefix of the body", which also retires the
  `TRACE_SEARCH_WINDOW = 8` magic number.
- **Per-payload removal** inside one function, independently.
- **Include management for free.** The `#include` line carries the same
  marker (`#include "util/ScopeTrace.h"  // @tj:scope_trace`), so removing a
  payload removes its include. This closes the "injected files do not
  compile because the header is missing" limitation.

Chosen over paired block sentinels (`// >>> ... // <<<`) because a trailing
token cannot lose its partner and keeps `git diff` readable.

`LEGACY_MARKERS = ["ScopeTrace trace"]` keeps `remove` able to clean up code
injected by the current version, which has no markers.

### Inject becomes a sync, not an append

`already_injected` currently skips on sight, so editing a payload template
never updates already-injected code. With markers, injection can instead:
read the marked prefix, regenerate the payloads this rule names, leave
markers it does not name untouched, and rewrite the region in declared
order. Injection stays idempotent and template edits take effect on rerun.

Log lines change accordingly: `🔄 Updated` when the text differs, `✅ Up to
date` when it does not.

## Parameter injection: three hard problems

**1. `default_check`'s `static_assert` breaks the build.** The fallback
branch fires at compile time for any type without an explicit branch. Fine
for hand-written calls; injected across hundreds of functions it means the
first unlisted parameter type (`std::string`, `SymbolType`, any template
parameter) fails the build, at a line nobody wrote.

Rejected fix: a type allowlist in the injector config. It forces the
injector to know the project's type system, and forgetting to update the
JSON breaks the build.

**Chosen fix: let C++ decide, via SFINAE.** The injector stays ignorant of
types.

```cpp
template<typename T, typename = void>
struct check_traits : std::false_type {};

template<typename T>
inline constexpr bool has_check_v = check_traits<T>::value;

template<typename T>
bool default_check(const T& value) {
    if constexpr (has_check_v<T>) return check_traits<T>::valid(value);
    else return true;                    // unregistered type: pass, not a compile error
}
```

Types register themselves next to their own definition:

```cpp
template<> struct check_traits<TradeData> : std::true_type {
    static bool valid(const TradeData& v) { return v.price_ > 0.0 && v.timestamp_ms_ > 0; }
};
```

Three wins: injected code always compiles (failure mode is a missed check,
not a broken build); type knowledge lives with the type; and
`ParameterCheck.h` no longer needs `#include "../src/Types.h"`, so the
generic checker stops reaching into `src` for domain types.

**2. Unnamed parameters, templates, variadics.** `void f(int)` reports
`spelling == ""`. If any parameter is unnamed, skip the whole payload for
that function and log it — silently dropping one argument would misalign
names against values. Same for template and variadic functions, initially.

**3. Ignore the return value.** `check_all` returns `bool`, but injecting
`if (!check_all(...)) return;` cannot work: the return type varies
(`void`/`T`/`T&`) and the injector has no correct value to return, and
control flow cannot be compiled out. `check_all` already logs, so discarding
the result is correct. Acting on a bad parameter is the caller's job.

## ParameterCheck.h changes

Ordered by impact.

1. **`is_integral_v` returning `value > 0` is the biggest problem.** It flags
   `bool false`, `char`, and every legitimately zero or negative quantity —
   empty-batch counts, indices, price deltas, positions, P&L. Injected
   everywhere it produces a log full of false positives, and then nobody
   reads the log. `default_check` should assert only what is universally true
   (pointers non-null, floats finite, containers non-empty); "must be
   positive" is a business rule and belongs in an explicit `check_traits`
   registration.
2. **Reopening the log file on every failure.** An `ofstream` open/close per
   bad parameter per call, on a hot path. `current_timestamp()` also uses
   `std::localtime`, which returns a shared static buffer and is not thread
   safe. `util/Logger.h` is already a thread-safe singleton with levels and
   file handling — route through `LOG(CustomerLogLevel::WARN)`.
3. **Take names as `std::initializer_list<const char*>`.** The `const char**`
   signature forces the injector to emit a separate `static const char*
   _tj_names[]` line first. With an initializer list the injected code is one
   clean line, and `names.size() != sizeof...(args)` becomes assertable —
   today `names[current_idx]` can run off the end unchecked.
4. Drop the 10-parameter limit and `dummy_names`; real names make them dead.
5. Fold the recursion with a C++17 fold expression using `&`, not `&&`, and
   comment that the non-short-circuit is deliberate — every parameter must be
   reported, and the next reader will otherwise "optimise" it to `&&`.

## ScopeTrace.h

There is no real `ScopeTrace` in the project yet; the only one is the empty
test stub at `tools/trace_injector/test/src/ScopeTrace.h` (which has two
stray backticks on its last line and would not compile — it is never
compiled, so nothing noticed).

```cpp
class ScopeTrace {
public:
    ScopeTrace(const char* file, int line, const char* func,
               uint8_t level = CustomerLogLevel::DEBUG);
    ~ScopeTrace();
    ScopeTrace(const ScopeTrace&) = delete;        // copying would log the exit twice
    ScopeTrace& operator=(const ScopeTrace&) = delete;
private:
    const char* func_;
    std::chrono::steady_clock::time_point start_;
};
```

- **Elapsed time in the destructor.** RAII gives it away free, and it is the
  real payoff of injecting everywhere: not just a call tree but a cost per
  level.
- **A `thread_local` depth counter for indentation.** Logs injected
  everywhere are unreadable without nesting.
- **`std::uncaught_exceptions()` in the destructor** to distinguish `exit`
  from `exit(exception)` — the path an early return does not cover.
- **A compile-time switch** collapsing the class to empty. This is what lets
  injected code stay in the source.
- Take the qualified name as a literal, not `__FUNCTION__`.
- Log through `Logger`, not `std::cout`.

## Order of work

1. Fix the header-line misplacement bug (one line, one test). Prerequisite:
   without it a misplaced `check_all` is a compile error.
2. Markers: `@tj:` on injected lines, removal by marker, legacy fallback.
   Still one built-in payload, so behaviour is unchanged, but removal stops
   matching on content.
3. Payload table and placeholders. `TRACE_LINES` becomes the built-in
   `scope_trace` default; `{indent}` and `{qualified_name}` retire the
   hardcoded indent and `__FUNCTION__`.
4. Parameter placeholders and `requires_parameters`, with the skip rules for
   unnamed/template/variadic.
5. Automatic `#include` management, same mechanism as markers.
6. Extend to `CONSTRUCTOR`, `DESTRUCTOR`, `FUNCTION_TEMPLATE`. Probing added
   three things the earlier draft did not know:
   - A constructor's member-init list has braces of its own and they come
     first, so the body brace has to come from the `COMPOUND_STMT` child
     rather than from a text scan.
   - An uninstantiated `FUNCTION_TEMPLATE` reports `is_definition()` false and
     exposes no body at all, so for that one kind the text decides — and a `;`
     before the `{` is what tells a declaration from a definition.
   - `get_arguments()` is empty for the same kind while the `PARM_DECL`
     children are there, so parameter payloads read the children instead.

   Bodies written on one line are skipped with a warning: nothing fits after
   the line without landing outside the braces.
7. C++ side: write `ScopeTrace.h`, apply the `ParameterCheck.h` changes.
   Independent of 1–6. Three things came out differently from the sketch above:
   - The default level is a macro (`SCOPE_TRACE_LEVEL`, `PARAMETER_CHECK_LEVEL`)
     rather than `CustomerLogLevel::DEBUG`. Naming the enum would mean
     `#include "../src/Types.h"` from `util`, which is the dependency this step
     is removing.
   - The generic `default_check` does **not** assert that a container is
     non-empty. "Non-empty" is a rule about a particular container, not about
     `std::vector`, and putting it in the generic layer would recreate exactly
     the `> 0` false-positive problem this step exists to fix. `DoubleVector`
     and `TradeDataVector` keep the rule by registering it in `src/Types.h`;
     `DoubleDeque` deliberately does not, an empty rolling window being an
     ordinary state on the first tick.
   - The fold over `&` indexes its names through an `std::index_sequence`
     rather than walking a pointer. `check_one_param(caller, *name++, args)`
     would leave the increments unsequenced, which is undefined — and the `&`
     itself has to stay, since `&&` would hide the second bad parameter.

   Landed as: `ScopeTrace.h` plus its test in `util`; `ParameterCheck.h`
   rewritten with `check_traits`; the six registrations and their test in the
   parent repo; the built-in payload switched to the qualified name.

Every step must leave `python test/run_tests.py` green, with new scenarios
and self checks added as the behaviour grows.
