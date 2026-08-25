#!/usr/bin/env python3
"""
State Machine JSON -> C++ Code Generator using Jinja2 Templates
"""
import argparse
import json
import re
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def load_json(json_path: str) -> dict:
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_existing_events(event_h_path: Path) -> set:
    if not event_h_path.exists():
        return set()

    content = event_h_path.read_text(encoding="utf-8")
    match = re.search(r'enum\s+class\s+Event\s*\{([^}]+)\}', content)
    if not match:
        return set()

    body = match.group(1)
    return {item.strip() for item in body.split(",") if item.strip()}


def prepare_context(data: dict, prefix: str, existing_events: set) -> dict:
    states = data.get("states", [])
    transitions = data.get("transitions", [])
    initial_state = data.get("initial_state", states[0]["name"] if states else "Idle")

    json_events = {t["event"] for t in transitions if t.get("event")}
    guards = sorted(list({t["guard"] for t in transitions if t.get("guard")}))
    actions = sorted(list({t["action"] for t in transitions if t.get("action")}))

    all_events = sorted(list(existing_events | json_events))

    return {
        "prefix": prefix,  # 确保这里使用的是确定的字符串，绝不为 None
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
    parser.add_argument("-o", "--output-dir", default=".", help="Directory to save generated C++ files")
    args = parser.parse_args()

    try:
        data = load_json(args.input)

        # 1. 优先使用命令行 -p 传入的值
        # 2. 其次读取 JSON 里的 "prefix"
        # 3. 若都没有，回退使用 "Order" 兜底
        target_prefix = args.prefix or data.get("prefix") or "Order"

        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        event_h_path = out_dir / "event.h"
        existing_events = parse_existing_events(event_h_path)

        # 把明确计算出来的 target_prefix 传入
        context = prepare_context(data, target_prefix, existing_events)

        env = Environment(
            loader=FileSystemLoader(args.template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )

        files_map = {
            "event.h.j2": "event.h",
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