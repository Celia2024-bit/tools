#!/usr/bin/env python3
"""
State Machine JSON -> Mermaid Diagram Converter Tool (with HTML Inline Styling)

Usage:
    python3 json_to_mermaid.py state_machine_2.json -o state_machine.mmd
"""
import argparse
import json
import sys
from pathlib import Path


def generate_mermaid(data: dict) -> str:
    lines = ["stateDiagram-v2"]

    states = data.get("states", [])
    transitions = data.get("transitions", [])
    initial_state = data.get("initial_state")

    # 1. Entry point
    if initial_state:
        lines.append(f"    [*] --> {initial_state}")

    # 2. Transitions with styled HTML inline elements
    for t in transitions:
        from_state = t.get("from")
        to_state = t.get("to")
        
        parts = []
        if t.get("event"):
            # Blue for Event
            parts.append(f"<font color='#0277bd'><b>{t['event']}</b></font>")
        if t.get("guard"):
            # Purple/Magenta for Guard
            parts.append(f"<font color='#8e24aa'>[{t['guard']}]</font>")
        if t.get("action"):
            # Dark Orange for Action
            parts.append(f"<font color='#e65100'>/ {t['action']}</font>")

        label = " ".join(parts).strip()
        if label:
            lines.append(f"    {from_state} --> {to_state} : {label}")
        else:
            lines.append(f"    {from_state} --> {to_state}")

    # 3. Exit points for final states
    final_states = [s["name"] for s in states if s.get("type") == "final"]
    for fs in final_states:
        lines.append(f"    {fs} --> [*]")

    lines.append("")

    # 4. State Node Colors
    initial_names = [s["name"] for s in states if s.get("type") == "initial"]
    for name in initial_names:
        lines.append("    classDef initialStyle fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;")
        lines.append(f"    class {name} initialStyle")

    normal_names = [s["name"] for s in states if s.get("type") == "normal"]
    if normal_names:
        lines.append("    classDef normalStyle fill:#f0f4c3,stroke:#afb42b,stroke-width:1px;")
        lines.append(f"    class {', '.join(normal_names)} normalStyle")

    if final_states:
        lines.append("    classDef finalStyle fill:#ffebee,stroke:#e53935,stroke-width:2px;")
        lines.append(f"    class {', '.join(final_states)} finalStyle")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="State Machine JSON -> Mermaid Diagram Converter")
    parser.add_argument("input", help="Input JSON file path")
    parser.add_argument("-o", "--output", help="Output Mermaid (.mmd / .md) file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    mermaid_code = generate_mermaid(data)

    if args.output:
        Path(args.output).write_text(mermaid_code, encoding="utf-8")
        print(f"✅ Mermaid diagram written to {args.output}")
    else:
        print("\n" + mermaid_code)


if __name__ == "__main__":
    main()