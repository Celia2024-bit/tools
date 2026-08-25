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


def generate_html_preview(mermaid_code: str, title: str = "State Machine Diagram") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <!-- Embed Mermaid.js via CDN -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'default',
                securityLevel: 'loose'
            }});
        }});
    </script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f8f9fa;
            margin: 0;
            padding: 40px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .card {{
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            padding: 30px;
            max-width: 90%;
            width: 800px;
            box-sizing: border-box;
        }}
        h2 {{
            margin-top: 0;
            color: #333333;
            font-size: 20px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>{title}</h2>
        <div class="mermaid">
{mermaid_code}
        </div>
    </div>
</body>
</html>
"""


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
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(mermaid_code, encoding="utf-8")
        print(f"✅ Mermaid diagram written to {args.output}")

        # Auto-generate HTML preview next to the output file
        html_path = out_path.with_suffix(".html")
        prefix = data.get("prefix", "State Machine")
        html_content = generate_html_preview(mermaid_code, title=f"{prefix} State Machine Diagram")
        html_path.write_text(html_content, encoding="utf-8")
        print(f"✅ HTML preview written to {html_path}")
    else:
        print("\n" + mermaid_code)


if __name__ == "__main__":
    main()