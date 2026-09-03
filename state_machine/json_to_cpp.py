#!/usr/bin/env python3
"""
State Machine JSON -> C++ Code Generator using Jinja2 Templates

Usage:
    # Generates C++ files into default directory ./out/code
    python3 json_to_cpp.py ./out/state_machine.json

    # Custom output directory
    python3 json_to_cpp.py ./out/state_machine.json -o ./generated_src
"""
import argparse
import json
import re
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def load_json(json_path: Path) -> dict:
    """Load and parse JSON file from path."""
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def parse_existing_events(event_h_path: Path) -> set:
    """Extract existing enum values from an existing event.h file to prevent duplicate definitions."""
    if not event_h_path.exists():
        return set()

    content = event_h_path.read_text(encoding="utf-8")
    match = re.search(r'enum\s+class\s+Event\s*\{([^}]+)\}', content)
    if not match:
        return set()

    body = match.group(1)
    return {item.strip() for item in body.split(",") if item.strip()}


def prepare_context(data: dict, prefix: str, existing_events: set) -> dict:
    """Build the context dictionary passed to Jinja2 templates."""
    states = data.get("states", [])
    transitions = data.get("transitions", [])
    initial_state = data.get("initial_state", states[0]["name"] if states else "Idle")

    json_events = {t["event"] for t in transitions if t.get("event")}
    guards = sorted(list({t["guard"] for t in transitions if t.get("guard")}))
    actions = sorted(list({t["action"] for t in transitions if t.get("action")}))

    all_events = sorted(list(existing_events | json_events))

    return {
        "prefix": prefix,
        "initial_state": initial_state,
        "states": states,
        "transitions": transitions,
        "events": all_events,
        "guards": guards,
        "actions": actions,
        "contexts": data.get("contexts", [])
    }


def main():
    parser = argparse.ArgumentParser(description="Generate C++ State Machine files.")
    parser.add_argument("input", help="Path to input JSON file")
    parser.add_argument("-p", "--prefix", default=None, help="Prefix for class names (overrides JSON config)")
    parser.add_argument("-t", "--template-dir", default="./templates", help="Directory containing Jinja2 templates")
    parser.add_argument("-o", "--output-dir", default="./out/code", help="Directory to save generated C++ files (defaults to ./out/code)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        data = load_json(input_path)

        # 1. Command-line argument -p takes highest precedence
        # 2. Fall back to JSON "prefix" field
        # 3. Fall back to "Order" as default
        target_prefix = args.prefix or data.get("prefix") or "Order"

        # Output directory defaults to ./out/code
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        event_h_path = out_dir / "event.h"
        existing_events = parse_existing_events(event_h_path)

        context = prepare_context(data, target_prefix, existing_events)

        env = Environment(
            loader=FileSystemLoader(args.template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )

        files_map = {
            "event.h.j2": "event.h",
            "main.cpp.j2": "main.cpp",
            "context.h.j2": f"{target_prefix}Context.h",
            "handler.h.j2": f"{target_prefix}Handler.h",
            "handler.cpp.j2": f"{target_prefix}Handler.cpp",
            "state_machine.h.j2": f"{target_prefix}StateMachine.h",
            "state_machine.cpp.j2": f"{target_prefix}StateMachine.cpp",
        }

        print(f"⚙️ Generating C++ files with prefix '{target_prefix}' into directory: {out_dir.resolve()}")
        for tmpl_name, out_name in files_map.items():
            template = env.get_template(tmpl_name)
            content = template.render(context)
            target_path = out_dir / out_name
            target_path.write_text(content, encoding="utf-8")
            print(f"   └─ ✅ {out_name}")

        print("\n✨ Code generation completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()