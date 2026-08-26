#!/usr/bin/env python3

import json
import argparse
from pathlib import Path

from clang import cindex

from logger import Logger


TRACE_LINES = [
    "    ScopeTrace trace(\n",
    "        __FILE__,\n",
    "        __LINE__,\n",
    "        __FUNCTION__\n",
    "    );\n",
    "\n",
]


def load_config(config_file):

    with open(
        config_file,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


def find_cpp_files(directory, file_name):

    root = Path(directory)

    if not file_name:
        return list(
            root.rglob("*.cpp")
        )

    result = []

    for cpp in root.rglob("*.cpp"):

        if cpp.name == file_name:
            result.append(cpp)

    return result

def match_function(
    current_name,
    requested_name
):

    if not requested_name:
        return True

    return current_name == requested_name


def already_injected(
    lines,
    brace_idx
):

    begin = brace_idx + 1
    end = min(
        brace_idx + 8,
        len(lines)
    )

    for i in range(begin, end):

        if "ScopeTrace trace" in lines[i]:
            return True

    return False


def find_open_brace_line(
    lines,
    start_line,
    end_line
):

    begin = start_line - 1

    end = min(
        end_line,
        len(lines)
    )

    for i in range(begin, end):

        if "{" in lines[i]:
            return i

    return None


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats
):

    index = cindex.Index.create()

    tu = index.parse(
        str(cpp_file),
        args=[
            "-x",
            "c++",
            "-std=c++17"
        ]
    )

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    insertions = []

    for node in tu.cursor.walk_preorder():
        
        if node.kind in (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.FUNCTION_DECL
        ):

            print(
                node.kind,
                node.spelling,
                node.extent.start.line,
                node.extent.end.line,
                node.is_definition()
            )
        
        if node.kind not in (
            cindex.CursorKind.CXX_METHOD,
            cindex.CursorKind.FUNCTION_DECL
        ):
            continue

        if not node.is_definition():
            continue

        if not match_function(
            node.spelling,
            target_function
        ):
            continue

        brace_idx = find_open_brace_line(
            lines,
            node.extent.start.line,
            node.extent.end.line
        )

        if brace_idx is None:
            continue

        if already_injected(
            lines,
            brace_idx
        ):
            logger.log(
                f"   ✅ Already injected: {node.spelling}()"
            )
            continue

        insertions.append(
            (
                brace_idx + 1,
                node.spelling
            )
        )

    if not insertions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up
    #
    insertions.sort(
        key=lambda x: x[0],
        reverse=True
    )

    for insert_idx, func_name in insertions:

        for entry in reversed(
            TRACE_LINES
        ):
            lines.insert(
                insert_idx,
                entry
            )

        logger.log(
            f"   ✨ Injected: {func_name}()"
        )

        stats["trace_injected"] += 1

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1


def process_rule(
    rule,
    logger,
    stats
):

    directory = rule.get(
        "directory",
        ""
    )

    file_name = rule.get(
        "file",
        ""
    )

    function_name = rule.get(
        "function",
        ""
    )

    cpp_files = find_cpp_files(
        directory,
        file_name
    )

    for cpp_file in cpp_files:

        stats["files_scanned"] += 1

        logger.log()
        logger.log(
            f"⚙️ Processing: {cpp_file}"
        )

        inject_trace_into_file(
            cpp_file,
            function_name,
            logger,
            stats
        )


def cleanup_logs():

    for file in Path.cwd().glob(
        "trace_injector_*.log"
    ):
        try:
            file.unlink()
        except Exception:
            pass


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default="config.json"
    )

    args = parser.parse_args()

    cleanup_logs()

    logger = Logger()

    config = load_config(
        args.config
    )

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "trace_injected": 0
    }

    logger.log(
        "================================================="
    )

    logger.log(
        "Trace Injector v1.1"
    )

    logger.log(
        "================================================="
    )

    for rule in config.get(
        "rules",
        []
    ):

        process_rule(
            rule,
            logger,
            stats
        )

    logger.log()
    logger.log(
        "================================================="
    )

    logger.log(
        "Summary"
    )

    logger.log(
        "================================================="
    )

    logger.log(
        f"Files Scanned  : {stats['files_scanned']}"
    )

    logger.log(
        f"Files Modified : {stats['files_modified']}"
    )

    logger.log(
        f"Trace Injected : {stats['trace_injected']}"
    )

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.close()


if __name__ == "__main__":
    main()