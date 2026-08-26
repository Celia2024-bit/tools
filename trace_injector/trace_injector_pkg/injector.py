from clang import cindex

from .constants import TRACE_LINES
from .file_discovery import match_function
from .line_utils import already_injected, find_open_brace_line


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats,
    excluded_functions=None
):

    if excluded_functions is None:
        excluded_functions = set()

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

        if node.spelling in excluded_functions:

            logger.log(
                f"   🚫 Excluded: {node.spelling}()"
            )
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
