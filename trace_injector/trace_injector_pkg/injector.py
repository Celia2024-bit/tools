from .constants import TRACE_LINES
from .line_utils import already_injected, find_open_brace_line
from .targets import (
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit
)


def inject_trace_into_file(
    cpp_file,
    target_function,
    logger,
    stats,
    excluded_functions=None,
    target_base_class="",
    include_dirs=None
):

    if excluded_functions is None:
        excluded_functions = set()

    tu = parse_translation_unit(
        cpp_file,
        include_dirs
    )

    if target_base_class:

        log_parse_problems(
            tu,
            logger
        )

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    insertions = []

    for node, label in iter_target_functions(
        tu,
        target_function,
        target_base_class,
        excluded_functions,
        logger
    ):

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
                f"   ✅ Already injected: {label}()"
            )
            continue

        insertions.append(
            (
                brace_idx + 1,
                label
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

    for insert_idx, label in insertions:

        for entry in reversed(
            TRACE_LINES
        ):
            lines.insert(
                insert_idx,
                entry
            )

        logger.log(
            f"   ✨ Injected: {label}()"
        )

        stats["trace_injected"] += 1

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1
