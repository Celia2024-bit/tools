# C++ Dynamic Parameter Check Generator

A compile-time static validation tool and dynamic header generator for C++ parameter checking. It uses Python and Jinja2 templates to automatically inject `#include` paths for target types and enforces strict compile-time checks via SFINAE and `static_assert`.

---

## Architecture & Directory Structure

```text
.
├── generate_parameter_check.py   # Code generation & path resolution script
├── templates/
│   ├── CheckTraits.h             # Base traits template for custom type rules
│   └── ParameterCheck.h.j2       # Jinja2 template for ParameterCheck.h
└── test/
    ├── include/
    │   ├── Types.h               # Valid custom types (isValid, empty, or traits)
    │   └── TypesInvalid.h        # Unprepared types (triggers static_assert)
    ├── main.cpp                  # Test suite
    └── output/                   # Generated headers deployment target
```

## Key Features

1. **Compile-Time Safety**: Uses `std::void_t` and SFINAE traits (`details::is_validatable_v`) inside `ParameterCheck.h`. If a custom type in `Types.h` lacks `isValid()`, `empty()`, or a `check_traits<T>` specialization, `clang++`/`g++` will fail immediately at compile time with a clear error message.

2. **Automatic Path Resolution**: Computes precise relative `#include` paths between the target output folder and `Types.h` / `CheckTraits.h`.

3. **Automated Deployment**: Automatically copies `CheckTraits.h` alongside the specified `Types.h` directory and outputs `ParameterCheck.h` to the destination directory.

4. **Validate First, Write Nothing On Failure**: `Types.h` is checked before the script touches anything. A rejected run leaves the target tree exactly as it found it — no `CheckTraits.h` copied, no output directory created, exit code 1.

## Prerequisites

- Python 3.7+

- Jinja2 (`pip install jinja2`)

- C++17 compliant compiler (`g++` or `clang++`)

## Usage & Execution Flow

### 1. Run Generation Script

Execute the Python script by passing the path to `Types.h` and the target output directory:

```bash
# Syntax: python generate_parameter_check.py <path_to_types_header> <output_dir> [--force]

python generate_parameter_check.py test/include/Types.h test/output
```

**Script Actions, in order:**

1. Validates `test/include/Types.h` (see *Type Preparation Rules*). On failure it prints why, writes nothing at all, and exits 1.

2. Copies `templates/CheckTraits.h` to `test/include/CheckTraits.h`.

3. Computes relative `#include` paths for both headers.

4. Renders `templates/ParameterCheck.h.j2` and writes the resulting `ParameterCheck.h` into `test/output/`.

Steps 2-4 are the only writes, and none of them run until step 1 passes.

A successful run:

```text
$ python generate_parameter_check.py test/include/Types.h test/output
--> Validating test\include\Types.h...
--> Types validation passed.
--> Successfully copied CheckTraits.h to Types directory: test\include\CheckTraits.h
--> Successfully generated: test\output\ParameterCheck.h
    * Includes Types.h from: '../include/Types.h'
    * Includes CheckTraits.h from: '../include/CheckTraits.h'
```

### 2. Rejected Runs and `--force`

Point the script at `TypesInvalid.h` and it stops at step 1. Note what is
*absent* from the output: no copy, no generation. `test/include/CheckTraits.h`
and `test/output/` are not created, so a failed run cannot leave the target
project half-provisioned.

```text
$ python generate_parameter_check.py test/include/TypesInvalid.h test/output
--> Validating test\include\TypesInvalid.h...
[Validation Failed] Enum 'ActionType' in TypesInvalid.h lacks 'check_traits<ActionType>' specialization.

[Build Stopped] Types validation failed. Generation aborted.
Nothing was written. Pass --force to generate regardless and let
the compile-time static_assert do the rejecting instead.

$ echo $?
1
```

`--force` reports the same failure and then generates anyway:

```text
$ python generate_parameter_check.py test/include/TypesInvalid.h test/output --force
--> Validating test\include\TypesInvalid.h...
[Validation Failed] Enum 'ActionType' in TypesInvalid.h lacks 'check_traits<ActionType>' specialization.
--> Types validation FAILED, generating anyway (--force).
    The compiler is expected to reject the result via static_assert.
--> Successfully copied CheckTraits.h to Types directory: test\include\CheckTraits.h
--> Successfully generated: test\output\ParameterCheck.h
    * Includes Types.h from: '../include/TypesInvalid.h'
    * Includes CheckTraits.h from: '../include/CheckTraits.h'

$ echo $?
0
```

Exit codes, for scripting the generator into a build:

| Run | Exit | Wrote anything? |
|---|---|---|
| Validation passed | 0 | yes |
| Validation failed | 1 | **no** |
| Validation failed, `--force` | 0 | yes |
| `Types.h` path not found | 1 | no |

`--force` is not an escape hatch for unprepared types. Its purpose is to let
the compile-time `static_assert` be exercised on purpose, as in *Testing
Compile-Time Interception* below — the static check is a fast, readable gate,
while the `static_assert` is the authority and sees types this script never
looks at (anything declared outside `Types.h`). Using `--force` to get past a
real complaint just moves the same failure to the compiler, with a longer error
message.

## Build & Run Tests

You can compile and run the test directly using `g++` with C++17 support 

### Normal Build (Valid Types)

```bash
# 1. Generate ParameterCheck.h for valid types
python generate_parameter_check.py test/include/Types.h test/output

# 2. Compile and run test prog
cd test 
g++ -std=c++17 main.cpp -o test_runner
./test_runner
```

### Testing Compile-Time Interception (Invalid Types)

To verify that unprepared custom types are blocked at compile time, run the
script against `TypesInvalid.h`. `--force` is required here: the static check
catches this file up front, so without it generation stops and you never reach
the compiler.

```bash
# 1. Generate ParameterCheck.h targeting unprepared types
python generate_parameter_check.py test/include/TypesInvalid.h test/output --force

# 2. Compilation will immediately fail with static_ass
cd test 
g++ -std=c++17 main.cpp -o test_runner
#In file included from output/ParameterCheck.h:12,
#                 from main.cpp:6:
#output/../include/CheckTraits.h: In instantiation of 'static bool check_traits<T, Enable>::check(const T&) [with T = ActionType; Enable = void]':
#output/../include/TypesInvalid.h:60:60:   required from here
#output/../include/CheckTraits.h:73:33: error: static assertion failed: default_check: No check available for this type.
#Fix by one of:
#  1) Add 'bool isValid() const' to the type, or
#  2) Make sure it has 'empty()' if it's container-like, or
#  3) Specialize check_traits<T> for this type (near the type's definition).
#   73 |         static_assert(sizeof(T) == 0,
#      |                       ~~~~~~~~~~^~~~
#output/../include/CheckTraits.h:73:33: note: the comparison reduces to '(4 == 0)'
```

## Type Preparation Rules

To pass the compile-time validation check, every custom type passed to `validate_params` or `default_validate` must satisfy **at least one** of the following:

1. **Member Function**: Implements `bool isValid() const`.

2. **Container Method**: Implements `.empty()` (e.g., `std::vector`, `std::string`).

3. **Trait Specialization**: Provides a `check_traits<T>` specialization inside or alongside `Types.h`.

The static check looks for a *specialization* — `struct check_traits<T>` — not
for the name `check_traits<T>` on its own. Merely calling
`check_traits<T>::check(...)` somewhere in the file does not make `T` prepared,
and used to be miscounted as if it did.

Comments are stripped before any of this runs, so prose about your types cannot
fail validation and a commented-out `isValid()` does not count as one.

Being regex-based, it has limits worth knowing: it only reads the one file it is
given, and it decides whether a type has `isValid()` by looking inside the
braces that follow its name. A type with an unusual body (a nested type, a `= {}`
initializer) can confuse that. When in doubt, the compiler is the authority.

Example (Valid `Types.h`)

```cpp
#include "CheckTraits.h"

// 1. Valid via isValid()
struct TradeData {
    double price;
    bool isValid() const { return price > 0.0; }
};

// 2. Valid via check_traits specialization
enum class ActionType { BUY, SELL };

template<>
struct check_traits<ActionType> {
    static bool check(const ActionType& type) {
        return type == ActionType::BUY || type == ActionType::SELL;
    }
};
```
