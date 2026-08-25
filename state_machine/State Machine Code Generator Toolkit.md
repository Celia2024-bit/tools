# State Machine Code Generator Toolkit

A lightweight Python toolchain that parses state machine specifications from Markdown tables, validates transition logic, exports structured JSON data, generates C++ code via Jinja2 templates, and renders Mermaid.js diagrams with interactive HTML previews.

---

## Tool Overview

- **`table_to_json.py`**: Converts Markdown state machine specifications into a validated JSON schema.
- **`json_to_cpp.py`**: Generates complete C++ source code (Headers, Handlers, State Machines) from JSON using Jinja2 templates.
- **`json_to_mermaid.py`**: Generates Mermaid diagram files (`.mmd`) and styled HTML preview pages (`.html`) with inline color highlighting.

---

## Prerequisites

- Python 3.8+
- [Jinja2](https://pypi.org/project/Jinja2/)

## Directory Structure

```
.
├── state_machine.md       # Input specification (Markdown table)
├── table_to_json.py       # Markdown -> JSON converter
├── json_to_cpp.py         # JSON -> C++ generator
├── json_to_mermaid.py     # JSON -> Mermaid & HTML preview generator
├── templates/             # Jinja2 template files (*.j2)
└── out/                   # Output directory (auto-created)
    ├── state_machine.json
    ├── state_machine.mmd
    ├── state_machine.html
    └── code/              # Generated C++ source files

```

## Usage

### 1. Markdown to JSON (`table_to_json.py`)

Parses state definition and transition tables, performs validation checks (e.g., dead states, conflicting transitions, orphan nodes), and outputs a structured JSON file.

Bash

```
# Default: Writes output to ./out/<input_name>.json
python3 table_to_json.py state_machine.md

# Custom output path
python3 table_to_json.py state_machine.md -o ./out/custom_machine.json

# Force output generation even if validation errors occur
python3 table_to_json.py state_machine.md --force
```

### 2. JSON to C++ Generator (`json_to_cpp.py`)

Generates context, event, handler, and state machine C++ headers and implementation files based on Jinja2 templates.

Bash

```
# Default: Writes code to ./out/code
python3 json_to_cpp.py ./out/state_machine.json

# Override class prefix (overrides JSON config prefix)
python3 json_to_cpp.py ./out/state_machine.json -p Order

# Custom output directory and template directory
python3 json_to_cpp.py ./out/state_machine.json -o ./src/generated -t ./custom_templates
```

### 3. JSON to Mermaid & HTML Preview (`json_to_mermaid.py`)

Generates a `.mmd` diagram file and an `.html` interactive preview with custom color-coded labels (Events in blue, Guards in purple, Actions in orange).

Bash

```
# Default: Generates state_machine.mmd and state_machine.html in the same directory as input
python3 json_to_mermaid.py ./out/state_machine.json

# Explicit custom output paths
python3 json_to_mermaid.py ./out/state_machine.json -om ./out/flow.mmd -oh ./out/flow.html
```

## Markdown Input Specification Format

Your input `.md` file must contain the following sections and headers:

Markdown

```
## Config
- prefix: Order

## Context Definition Table
| context_name | field_type | field_name | description || :--- | :--- | :--- | :--- || OrderContext | std::string | order_id | Unique identifier |
| OrderContext | double | amount | Order amount |

## State Definition Table
| id | name | type | description |
| :--- | :--- | :--- | :--- |
| S1 | Idle | initial | Initial state |
| S2 | PendingPayment | normal | Waiting for user payment |
| S3 | Completed | final | Order finished |

## State Transition Table
| id | from_state | event | guard | to_state | action | description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| T1 | Idle | CreateOrder | | PendingPayment | InitContext | Create new order |
| T2 | PendingPayment | PaySuccess | AmountValid | Completed | NotifyUser | Payment processed |
```

## Validation & Verification

`table_to_json.py` automatically performs static analysis on state tables prior to generation:

- **Errors**: Missing initial state, multiple initial states, duplicate state/transition IDs, transitions referencing undefined states, or conflicting transition rules.

- **Warnings**: Normal states without outgoing transitions (dead states) or defined states never referenced in any transition (orphan states).
