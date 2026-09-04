import argparse
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path
from google.genai import errors
import time

# Make sure this directory and every sub-tool directory come first on the import path
TOOLS_DIR = Path(__file__).resolve().parent
STATE_MACHINE_DIR = TOOLS_DIR / "state_machine"
SYNC_INTERFACE_DIR = TOOLS_DIR / "sync_interface"
ASPECT_INJECTOR_DIR = TOOLS_DIR / "aspect_injector"

for path in [TOOLS_DIR, STATE_MACHINE_DIR, SYNC_INTERFACE_DIR, ASPECT_INJECTOR_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

ROUTER_MODEL = "gemini-3.6-flash"

TOOL_LABELS = {
    "state_machine": "State Machine Generator",
    "interface_sync": "Interface Sync",
    "aspect_injector": "Aspect Injector",
    "unsupported": "Out of scope",
}

# Shown when the router cannot map a request onto any of the three tools
CAPABILITIES = [
    ("state_machine", "generate a C++ state machine (spec, diagram, code) from a description",
     "An order system that starts in Pending, moves to Paid on PaymentReceived, "
     "then to Completed on OrderDelivered."),
    ("interface_sync", "change a C++ interface header and sync every derived class",
     "Update interface include/IObserver_old.h: remove OnConnected, add "
     "OnError(int err_code). Sync all derived classes under test/src"),
    ("aspect_injector", "inject or remove trace / validate / guard aspects in C++ sources",
     "Add trace and validate logging to every function under test/src/hot, "
     "but skip AlphaEngine.cpp"),
]

ROUTER_SYSTEM_PROMPT = """You are an intent router for C++ automation tools.
Analyze the user's natural language request and determine which tool to use.

Tools available:
1. "state_machine": User wants to create or update a state machine.
2. "interface_sync": User wants to modify an existing C++ interface header and sync derived classes.
3. "aspect_injector": User wants to inject or remove aspects.
4. "unsupported": The request is anything else. These tools only generate and rewrite
   C++ source code, so use "unsupported" for general questions (weather, news, math),
   chit-chat, requests about other languages, or any task none of the three tools does.
   Never force an unrelated request into one of the three tools.

Rules:
- Output JSON ONLY in this format:
{
  "tool": "state_machine" | "interface_sync" | "aspect_injector" | "unsupported",
  "old_header": "<path to old header if mentioned in description, else null>",
  "src_dir": "<source directory for derived classes if mentioned, else null>",
  "reason": "<one short sentence; required when tool is unsupported, else null>"
}
- Do not wrap in markdown code fences.
"""

# Exit codes, so the web service can tell these apart from a crash
EXIT_UNSUPPORTED = 2
EXIT_ROUTER_UNAVAILABLE = 3

# --- progress reporting -------------------------------------------------------
# The web dashboard pipes this stdout straight into its log panel and also
# scrapes two markers out of it, so keep these two line shapes stable:
#   "-> AI selected tool: <tool>"
#   "-> artifact [<label>]: <path>"     (the path is always last on the line)
# Plain ASCII only: this output gets captured by consoles that are not UTF-8.
STEP_TOTAL = 3


def banner(title: str) -> None:
    bar = "=" * 62
    print(f"\n{bar}\n  {title}\n{bar}", flush=True)


def step(index: int, message: str) -> None:
    print(f"\n[{index}/{STEP_TOTAL}] {message}", flush=True)


def detail(message: str) -> None:
    print(f"      -> {message}", flush=True)


def bullet(message: str) -> None:
    print(f"         {message}", flush=True)


def rel_to_tools(path) -> str:
    """Shorten a path for logging, relative to the tools/ directory when possible."""
    try:
        return Path(path).resolve().relative_to(TOOLS_DIR).as_posix()
    except (ValueError, OSError):
        return str(path)


def report_artifact(label: str, path) -> None:
    detail(f"artifact [{label}]: {rel_to_tools(path)}")


def print_capabilities() -> None:
    """Tell the user what this assistant can actually do."""
    print("\nThis assistant only automates three C++ tasks:", flush=True)
    for index, (name, what, example) in enumerate(CAPABILITIES, start=1):
        print(f"  {index}. {name:<16} {what}", flush=True)
        print(f"     example: \"{example}\"", flush=True)


def handle_unsupported(description: str, reason: str) -> None:
    """Answer a request that none of the three tools can serve, changing nothing."""
    detail(f"reason: {reason or 'the request does not match any of the three C++ tools'}")
    print("\nNo tool was run, so nothing was generated or modified.", flush=True)
    print_capabilities()
    print(
        "\nRephrase the request in terms of one of the three tasks above and try again.",
        flush=True,
    )


def route_intent(description: str) -> dict:
    """Use Gemini to quickly determine which sub-tool to invoke, with auto-retry for 429 quota errors."""
    max_retries = 3
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        started = time.time()
        try:
            response = client.models.generate_content(
                model=ROUTER_MODEL,
                contents=description,
                config=types.GenerateContentConfig(
                    system_instruction=ROUTER_SYSTEM_PROMPT,
                    max_output_tokens=200,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL
                    ),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            intent = json.loads(text.strip())
            detail(f"Gemini answered in {time.time() - started:.1f}s")
            return intent

        except errors.ClientError as e:
            if e.code == 429 and attempt < max_retries - 1:
                detail(
                    f"Gemini rate limit (429), retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
                retry_delay *= 2  # exponential backoff
            else:
                raise e


def resolve_path(path_str: str, default_path: Path = None) -> Path:
    """
    Resolve any user-supplied path to a physical absolute path, relative or not.
    python nl_dev_tool.py "Add trace and validate logging to every function under aspect_injector/test/src/hot, but skip AlphaEngine.cpp"
    """
    if not path_str:
        return default_path.resolve() if default_path else None

    p = Path(path_str)
    # A relative path is resolved against the directory the command was run from
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    # Fall back to the default when the resolved path does not exist
    if not p.exists() and default_path and default_path.exists():
        return default_path.resolve()

    return p


def markdown_table_rows(md_text: str, section_title: str) -> list:
    """Return the data rows (as cell lists) of the '## <section_title>' markdown table."""
    rows = []
    in_section = False

    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = stripped.lstrip("#").strip().lower() == section_title.lower()
            continue
        if not in_section or not stripped.startswith("|"):
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        if cells and cells[0].startswith("**"):
            continue  # header row
        rows.append(cells)

    return rows


def summarize_state_machine_spec(md_text: str) -> None:
    """Log what the model actually designed, so the output shows real AI decisions."""
    try:
        states = [r[1] for r in markdown_table_rows(md_text, "State Definition Table") if len(r) > 1]
        transitions = markdown_table_rows(md_text, "State Transition Table")
        events = [r[2] for r in transitions if len(r) > 2]
        context_fields = markdown_table_rows(md_text, "Context Definition Table")
    except Exception as e:
        detail(f"could not summarize the generated spec: {e}")
        return

    if states:
        detail(f"AI designed {len(states)} states: {', '.join(states)}")
    if transitions:
        unique_events = list(dict.fromkeys(events))
        detail(f"AI designed {len(transitions)} transitions on events: {', '.join(unique_events)}")
    if context_fields:
        detail(f"AI designed {len(context_fields)} context field(s)")


def summarize_header_rewrite(old_text: str, new_text: str) -> None:
    """Log the interface lines the model added or dropped."""
    changed = [
        line for line in difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(), lineterm="", n=0
        )
        if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
    ]
    additions = sum(1 for line in changed if line.startswith("+"))
    detail(f"AI rewrote the interface: +{additions} / -{len(changed) - additions} lines")

    for line in changed[:20]:
        bullet(line)
    if len(changed) > 20:
        bullet(f"... {len(changed) - 20} more changed lines")


def summarize_aspect_config(config_data: dict) -> None:
    """Log the rules the model derived from the request."""
    for section in ("inject", "remove", "exclude"):
        rules = config_data.get(section) or []
        if not rules:
            continue

        detail(f"AI produced {len(rules)} {section} rule(s)")
        for rule in rules:
            parts = []
            if rule.get("directory"):
                parts.append(f"dir={rel_to_tools(rule['directory'])}")
            for key in ("file", "base_class", "function"):
                if rule.get(key):
                    parts.append(f"{key}={rule[key]}")
            if rule.get("inject_type"):
                parts.append(f"types=[{', '.join(rule['inject_type'])}]")
            bullet(f"- {'  '.join(parts) if parts else '(match everything)'}")

    include_dirs = config_data.get("include_dirs") or []
    if include_dirs:
        detail(f"include_dirs: {', '.join(rel_to_tools(d) for d in include_dirs)}")


def handle_state_machine(description: str, output: str, should_run: bool):
    """Generate a state machine spec from plain English, then build and run it.
    python  nl_dev_tool.py "An order processing system that starts in Pending, moves to Paid on PaymentReceived, and then moves to Completed on OrderDelivered."
    """
    from nl_to_state_machine import nl_to_state_machine_md, run_pipeline

    default_out = STATE_MACHINE_DIR / "test" / "state_machine.md"
    out_path = resolve_path(output, default_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    step(2, "Gemini is drafting the state machine specification...")
    started = time.time()
    md_content = nl_to_state_machine_md(description)
    detail(f"spec drafted in {time.time() - started:.1f}s ({len(md_content.splitlines())} lines)")
    summarize_state_machine_spec(md_content)

    out_path.write_text(md_content, encoding="utf-8")
    report_artifact("state machine spec", out_path)

    if not should_run:
        step(3, "Pipeline skipped (--no-run): the spec was generated only.")
        return

    step(3, "Running the deterministic pipeline: markdown -> json -> mermaid -> C++ ...")
    run_pipeline(out_path, cwd=STATE_MACHINE_DIR)


def handle_interface_sync(description: str, intent: dict, args, should_run: bool):
    """Rewrite an interface header and sync every derived class.
    python nl_dev_tool.py "Update interface sync_interface/test/include/IObserver_old.h: remove OnConnected, add OnError(int err_code), change OnData(int id, double timestamp). Sync all derived classes under sync_interface/test/src"
    """
    from nl_to_new_interface import generate_new_header

    # 1. Pick the paths: what the AI extracted wins, CLI arguments are the fallback
    raw_old = intent.get("old_header") or args.old
    raw_src = intent.get("src_dir") or args.src

    # 2. Turn them into absolute paths (accepts absolute paths and paths relative to the shell cwd)
    default_src = SYNC_INTERFACE_DIR / "test" / "src"
    src_dir = resolve_path(raw_src, default_src)

    if not raw_old:
        print("Error: Interface sync requires old header path. Mention it in description or use `--old <path>`.", file=sys.stderr)
        sys.exit(1)

    old_path = resolve_path(raw_old)
    if not old_path or not old_path.is_file():
        print(f"Error: Old header file not found at: {old_path}", file=sys.stderr)
        sys.exit(1)

    # 3. Generate the new header
    step(2, "Gemini is rewriting the interface header...")
    detail(f"old header: {rel_to_tools(old_path)}")
    detail(f"derived class root: {rel_to_tools(src_dir)}")

    old_text = old_path.read_text(encoding="utf-8")
    started = time.time()
    new_text = generate_new_header(old_text, description)
    detail(f"header generated in {time.time() - started:.1f}s")
    summarize_header_rewrite(old_text, new_text)

    if args.output:
        new_path = resolve_path(args.output)
    else:
        stem = old_path.stem
        new_stem = stem[:-4] if stem.endswith("_old") else f"{stem}_new"
        new_path = old_path.with_name(f"{new_stem}{old_path.suffix}")

    new_path.write_text(new_text, encoding="utf-8")
    report_artifact("updated header", new_path)

    # 4. Run the underlying sync script (always with absolute paths)
    if not should_run:
        step(3, "Sync skipped (--no-run): the header was generated only.")
        return

    abs_old = str(old_path)
    abs_new = str(new_path)
    abs_src = str(src_dir)

    step(3, f"Propagating the change to every derived class under {rel_to_tools(src_dir)} ...")
    detail(f"interface_sync.py --old {abs_old} --new {abs_new} --src {abs_src}")
    subprocess.run([
        sys.executable, str(SYNC_INTERFACE_DIR / "interface_sync.py"),
        "--old", abs_old,
        "--new", abs_new,
        "--src", abs_src
    ], check=True, cwd=SYNC_INTERFACE_DIR)


def handle_aspect_injector(description: str, output: str, should_run: bool):
    """Turn plain English into an aspect config, then inject or remove the aspects."""
    from nl_to_aspect_config import nl_to_config_json

    default_out = ASPECT_INJECTOR_DIR / "config.json"
    out_path = resolve_path(output, default_out)

    step(2, "Gemini is translating the request into an aspect injection config...")
    started = time.time()
    config_str = nl_to_config_json(description)
    detail(f"config generated in {time.time() - started:.1f}s")

    # Normalize the directory paths inside the generated config
    try:
        config_data = json.loads(config_str)

        # Rewrite every rule directory into an absolute path
        def clean_dir(target_list):
            for item in target_list:
                d = item.get("directory", "")
                if d:
                    # Strip a leading "aspect_injector/" prefix if the model added one
                    p = Path(d)
                    parts = p.parts
                    if len(parts) > 0 and parts[0] == "aspect_injector":
                        d = str(Path(*parts[1:]))

                    # Make it absolute against ASPECT_INJECTOR_DIR so cwd can never matter
                    abs_dir = (ASPECT_INJECTOR_DIR / d).resolve()
                    if abs_dir.exists():
                        item["directory"] = str(abs_dir)
                    else:
                        item["directory"] = d

        for section in ("inject", "remove", "exclude"):
            if section in config_data:
                clean_dir(config_data[section])

        summarize_aspect_config(config_data)
        config_str = json.dumps(config_data, indent=2)
    except Exception as e:
        print(f"Warning: Config path normalization failed: {e}")

    out_path.write_text(config_str, encoding="utf-8")
    report_artifact("aspect config", out_path)

    if not should_run:
        step(3, "Injection skipped (--no-run): the config was generated only.")
        return

    step(3, "Running the libclang-based injector over the matched sources...")
    detail(f"aspect_injector.py --config {out_path}")
    subprocess.run([
        sys.executable, str(ASPECT_INJECTOR_DIR / "aspect_injector.py"),
        "--config", str(out_path)
    ], check=True, cwd=ASPECT_INJECTOR_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="Single natural-language interface for all C++ automation tools."
    )
    parser.add_argument("description", help="Plain-English description of what you want to do")
    parser.add_argument("--old", default=None, help="Path to old interface header (for interface_sync)")
    parser.add_argument("--src", default=None, help="Source directory for derived classes")
    parser.add_argument("-o", "--output", default=None, help="Output path (optional)")
    parser.add_argument("--no-run", action="store_true", help="Only generate files, do not execute pipeline")
    args = parser.parse_args()

    should_run = not args.no_run

    banner("AI C++ DEV ASSISTANT")
    print(f"  request : {args.description}", flush=True)
    print(f"  mode    : {'generate + run' if should_run else 'generate only (--no-run)'}", flush=True)

    step(1, f"Asking Gemini ({ROUTER_MODEL}) which tool this request needs...")
    try:
        intent = route_intent(args.description)
    except errors.APIError as e:
        # Quota exhausted, bad key, service down: say so instead of dumping a traceback
        message = getattr(e, "message", None) or str(e)
        print(
            f"\nThe Gemini router is unavailable: {getattr(e, 'code', '?')} {message}",
            file=sys.stderr,
        )
        print("Nothing was generated or modified. Try again later.", file=sys.stderr)
        sys.exit(EXIT_ROUTER_UNAVAILABLE)

    tool = intent.get("tool")
    detail(f"AI selected tool: {tool}  ({TOOL_LABELS.get(tool, 'unknown tool')})")
    detail(
        f"AI extracted hints: old_header={intent.get('old_header') or '<none>'}, "
        f"src_dir={intent.get('src_dir') or '<none>'}"
    )

    if tool == "state_machine":
        handle_state_machine(args.description, args.output, should_run)
    elif tool == "interface_sync":
        handle_interface_sync(args.description, intent, args, should_run)
    elif tool == "aspect_injector":
        handle_aspect_injector(args.description, args.output, should_run)
    else:
        # "unsupported", or a tool name we do not know: never guess, never touch files
        handle_unsupported(args.description, intent.get("reason"))
        banner("OUT OF SCOPE - no tool was run")
        sys.exit(EXIT_UNSUPPORTED)

    banner(f"COMPLETED - {TOOL_LABELS.get(tool, tool)}")


if __name__ == "__main__":
    main()
