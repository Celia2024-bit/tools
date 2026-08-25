#!/usr/bin/env python3
"""
State Machine JSON -> Mermaid Diagram & HTML Preview Generator

Converts state machine definitions in JSON format into both Mermaid diagram (.mmd)
files and standalone HTML preview (.html) files with custom inline styling.

Usage:
    # Auto-generates input_file.mmd and input_file.html in the same directory
    python3 json_to_mermaid.py state_machine.json

    # Custom output paths for MMD and HTML files
    python3 json_to_mermaid.py state_machine.json -om ./out/flow.mmd -oh ./out/flow.html
"""
import argparse
import json
import sys
from pathlib import Path


def generate_mermaid(data: dict) -> str:
    """
    Parses JSON state machine data and generates a Mermaid stateDiagram-v2 string.
    
    Applies HTML inline font styling for transition labels (events, guards, actions)
    and classDef directives for state node coloring.
    """
    lines = ["stateDiagram-v2"]

    states = data.get("states", [])
    transitions = data.get("transitions", [])
    initial_state = data.get("initial_state")

    # 1. Entry point definition
    if initial_state:
        lines.append(f"    [*] --> {initial_state}")

    # 2. Process transitions with styled HTML inline elements
    for t in transitions:
        from_state = t.get("from")
        to_state = t.get("to")
        if not from_state or not to_state:
            continue

        parts = []
        if t.get("event"):
            # Blue color styling for Event
            parts.append(f"<font color='#0277bd'><b>{t['event']}</b></font>")
        if t.get("guard"):
            # Purple/Magenta color styling for Guard condition
            parts.append(f"<font color='#8e24aa'>[{t['guard']}]</font>")
        if t.get("action"):
            # Dark Orange color styling for Action execution
            parts.append(f"<font color='#e65100'>/ {t['action']}</font>")

        label = " ".join(parts).strip()
        if label:
            lines.append(f"    {from_state} --> {to_state} : {label}")
        else:
            lines.append(f"    {from_state} --> {to_state}")

    # 3. Exit points for terminal/final states
    final_states = [s["name"] for s in states if s.get("type") == "final"]
    for fs in final_states:
        lines.append(f"    {fs} --> [*]")

    lines.append("")

    # 4. Define and assign CSS color styles for state nodes
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
    """
    Wraps the generated Mermaid syntax into a standalone HTML template.
    
    Includes Mermaid.js from CDN with 'loose' security level to enable HTML label parsing.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <!-- Embed Mermaid.js library via CDN -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'default',
                securityLevel: 'loose'  // Required to parse inline HTML tags (<font>) inside labels
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
    parser = argparse.ArgumentParser(description="State Machine JSON -> Mermaid Diagram & HTML Preview Generator")
    parser.add_argument("input", help="Input JSON file path")
    parser.add_argument("-om", "--output-mmd", help="Output Mermaid (.mmd) file path")
    parser.add_argument("-oh", "--output-html", help="Output HTML (.html) file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    # Determine output paths: default to same directory and filename with corresponding extensions
    mmd_path = Path(args.output_mmd) if args.output_mmd else input_path.with_suffix(".mmd")
    html_path = Path(args.output_html) if args.output_html else input_path.with_suffix(".html")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    mermaid_code = generate_mermaid(data)

    # 1. Save .mmd file
    mmd_path.parent.mkdir(parents=True, exist_ok=True)
    mmd_path.write_text(mermaid_code, encoding="utf-8")
    print(f"✅ Mermaid diagram written to {mmd_path}")

    # 2. Save .html preview file
    prefix = data.get("prefix", "State Machine")
    html_content = generate_html_preview(mermaid_code, title=f"{prefix} State Machine Diagram")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_content, encoding="utf-8")
    print(f"✅ HTML preview written to {html_path}")


if __name__ == "__main__":
    main()