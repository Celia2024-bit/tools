#!/usr/bin/env python3
"""
State Machine Markdown Table -> JSON Converter

Usage:
    python3 table_to_json.py state_machine.md -o state_machine.json

Input file format (.md or .txt):
    Two sections, each introduced by a heading and followed by a markdown table:
      - "## State Definition Table" (or "## 状态定义表")
      - "## State Transition Table" (or "## 状态转移表")
    See state_machine.md for a full example.
"""
import argparse
import json
import sys
from pathlib import Path

STATE_COLUMNS = ["id", "name", "type", "description"]
TRANSITION_COLUMNS = ["id", "from_state", "event", "guard", "to_state", "action", "description"]
VALID_TYPES = {"initial", "final", "normal", ""}


def _strip_markdown_emphasis(cell: str) -> str:
    """Strip **bold**/*italic* markers and surrounding whitespace from a table cell."""
    cell = cell.strip()
    cell = cell.strip("*").strip()
    return cell


def parse_markdown_tables(path: str) -> dict:
    """Parse all markdown tables in a file, grouped by the nearest preceding '## Heading'.
    Returns {heading_text: [row_dict, row_dict, ...]}"""
    text = Path(path).read_text(encoding="utf-8")

    sections = {}
    current_title = None
    current_rows = []  # list[list[str]], first row is the header

    def flush():
        nonlocal current_rows, current_title
        if current_title and current_rows:
            header, *data_rows = current_rows
            rows = [dict(zip(header, row)) for row in data_rows]
            sections[current_title] = rows
        current_rows = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [_strip_markdown_emphasis(c) for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):  # skip |---|---| separator rows
            continue
        current_rows.append(cells)
    flush()

    return sections


def _find_section(sections: dict, en_keyword: str, zh_keyword: str, path: str) -> str:
    key = next((k for k in sections if en_keyword.lower() in k.lower() or zh_keyword in k), None)
    if key is None:
        raise ValueError(
            f"Could not find a table titled with '{en_keyword}' (or '{zh_keyword}') in {path}. "
            f"Expected a heading like '## {en_keyword}'."
        )
    return key


def _get_section(sections: dict, en_keyword: str, zh_keyword: str, columns: list, path: str) -> list:
    key = _find_section(sections, en_keyword, zh_keyword, path)
    rows = []
    for row in sections[key]:
        rows.append({col: row.get(col, "").strip() for col in columns})
    return rows


def load_states(path: str) -> list:
    sections = parse_markdown_tables(path)
    rows = _get_section(sections, "State Definition", "状态定义", STATE_COLUMNS, path)
    for row in rows:
        row["type"] = (row["type"] or "normal").lower()
    return rows


def load_transitions(path: str) -> list:
    sections = parse_markdown_tables(path)
    return _get_section(sections, "State Transition", "状态转移", TRANSITION_COLUMNS, path)


def validate(states: list, transitions: list) -> list:
    """Returns a list of (level, message). level='error' blocks generation, 'warning' is informational only."""
    issues = []

    # ---- State definition table checks ----
    for i, row in enumerate(states):
        line = i + 1
        if not row["name"]:
            issues.append(("error", f"[States] Row {line}: 'name' must not be empty"))
        if row["type"] not in VALID_TYPES:
            issues.append(("error", f"[States] Row {line}: type='{row['type']}' is invalid, "
                                     f"must be one of initial / final / normal"))

    ids = [r["id"] for r in states if r["id"]]
    dup_ids = {i for i in ids if ids.count(i) > 1}
    if dup_ids:
        issues.append(("error", f"[States] Duplicate id(s) found: {', '.join(sorted(dup_ids))}"))

    names = [r["name"] for r in states if r["name"]]
    dup_names = {n for n in names if names.count(n) > 1}
    if dup_names:
        issues.append(("error", f"[States] Duplicate state name(s) found: {', '.join(sorted(dup_names))}"))

    initial_states = [r for r in states if r["type"] == "initial"]
    if len(initial_states) == 0:
        issues.append(("error", "[States] No state with type=initial found; exactly one is required"))
    elif len(initial_states) > 1:
        names_str = ", ".join(r["name"] for r in initial_states)
        issues.append(("error", f"[States] Multiple states with type=initial found ({names_str}); "
                                 f"only one is allowed"))

    final_names = {r["name"] for r in states if r["type"] == "final"}
    normal_names = {r["name"] for r in states if r["type"] == "normal"}
    all_names = {r["name"] for r in states if r["name"]}

    # ---- State transition table checks ----
    for i, row in enumerate(transitions):
        line = i + 1
        if not row["from_state"]:
            issues.append(("error", f"[Transitions] Row {line}: 'from_state' must not be empty"))
        if not row["event"]:
            issues.append(("error", f"[Transitions] Row {line}: 'event' must not be empty"))
        if not row["to_state"]:
            issues.append(("error", f"[Transitions] Row {line}: 'to_state' must not be empty"))
        if row["from_state"] and row["from_state"] not in all_names:
            issues.append(("error", f"[Transitions] Row {line}: from_state '{row['from_state']}' "
                                     f"is not defined in the state definition table"))
        if row["to_state"] and row["to_state"] not in all_names:
            issues.append(("error", f"[Transitions] Row {line}: to_state '{row['to_state']}' "
                                     f"is not defined in the state definition table"))

    tids = [r["id"] for r in transitions if r["id"]]
    dup_tids = {i for i in tids if tids.count(i) > 1}
    if dup_tids:
        issues.append(("error", f"[Transitions] Duplicate id(s) found: {', '.join(sorted(dup_tids))}"))

    # Dead state: a 'normal' state with no outgoing transition is likely a mistake
    # (it was probably meant to be 'final').
    states_with_outgoing = {r["from_state"] for r in transitions if r["from_state"]}
    for s in normal_names:
        if s not in states_with_outgoing:
            issues.append(("warning", f"State '{s}' (normal) has no outgoing transition. "
                                       f"If it should be a terminal state, set its type to 'final'."))

    # Orphan state: defined but never referenced by any transition
    referenced = states_with_outgoing | {r["to_state"] for r in transitions if r["to_state"]}
    for s in all_names:
        if s not in referenced:
            issues.append(("warning", f"State '{s}' is defined but never appears in any transition"))

    # Conflicting transitions: same from_state+event+guard mapped to different to_state
    seen = {}
    for i, row in enumerate(transitions):
        line = i + 1
        key = (row["from_state"], row["event"], row["guard"])
        if key in seen:
            prev_target, prev_line = seen[key]
            if prev_target != row["to_state"]:
                issues.append((
                    "error",
                    f"[Transitions] Conflict: from '{row['from_state']}' on event '{row['event']}' "
                    f"(guard='{row['guard']}'), row {prev_line} targets '{prev_target}', "
                    f"but row {line} targets '{row['to_state']}'"
                ))
        else:
            seen[key] = (row["to_state"], line)

    return issues


def build_json(states: list, transitions: list) -> dict:
    initial_name = next(r["name"] for r in states if r["type"] == "initial")

    states_json = [{
        "id": r["id"] or None,
        "name": r["name"],
        "type": r["type"],
        "description": r["description"] or None,
    } for r in states if r["name"]]

    transitions_json = [{
        "id": r["id"] or None,
        "from": r["from_state"],
        "event": r["event"],
        "guard": r["guard"] or None,
        "to": r["to_state"],
        "action": r["action"] or None,
        "description": r["description"] or None,
    } for r in transitions if r["from_state"]]

    return {
        "initial_state": initial_name,
        "states": states_json,
        "transitions": transitions_json,
    }


def main():
    parser = argparse.ArgumentParser(description="State Machine Markdown Table -> JSON Converter")
    parser.add_argument("input", help="Input file (.md or .txt)")
    parser.add_argument("-o", "--output", default="state_machine.json", help="Output JSON path")
    parser.add_argument("--force", action="store_true", help="Generate JSON even if error-level issues are found")
    args = parser.parse_args()

    states = load_states(args.input)
    transitions = load_transitions(args.input)

    issues = validate(states, transitions)
    errors = [m for lvl, m in issues if lvl == "error"]
    warnings = [m for lvl, m in issues if lvl == "warning"]

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"   - {w}")

    if errors:
        print("\nErrors found, please fix the table and retry:")
        for e in errors:
            print(f"   - {e}")
        if not args.force:
            print(f"\n{len(errors)} error(s), JSON not generated. (use --force to generate anyway)")
            sys.exit(1)
        else:
            print(f"\n{len(errors)} error(s), but --force was used, generating JSON anyway.")

    result = build_json(states, transitions)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nDone: {args.output}")
    print(f"   states: {len(result['states'])}, transitions: {len(result['transitions'])}")


if __name__ == "__main__":
    main()
