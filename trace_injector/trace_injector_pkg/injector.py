from .constants import SCOPE_TRACE
from .line_utils import (
    already_injected,
    find_legacy_trace_line,
    find_open_brace_line,
    insert_point
)
from .payloads import BUILT_IN_PAYLOADS, build_context, render
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
    include_dirs=None,
    payload_names=None,
    payload_table=None
):

    if excluded_functions is None:
        excluded_functions = set()

    if payload_table is None:
        payload_table = BUILT_IN_PAYLOADS

    if payload_names is None:
        payload_names = [SCOPE_TRACE]

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

        #
        # The legacy check keeps a rerun over a tree injected by an older
        # version from stacking a second trace on top of the first.
        #
        legacy_present = find_legacy_trace_line(
            lines,
            brace_idx
        ) is not None

        missing = [
            name
            for name in payload_names
            if not already_injected(
                lines,
                brace_idx,
                name
            )
            and not (
                name == SCOPE_TRACE
                and
                legacy_present
            )
        ]

        if not missing:

            logger.log(
                f"   ✅ Already injected: {label}()"
            )
            continue

        context = build_context(
            node,
            label,
            lines,
            brace_idx
        )

        new_lines = []

        for name in missing:

            new_lines.extend(
                render(
                    name,
                    payload_table[name],
                    context
                )
            )

        at, needs_separator = insert_point(
            lines,
            brace_idx
        )

        if needs_separator:
            new_lines.append("\n")

        insertions.append(
            (
                at,
                new_lines,
                label
            )
        )

    if not insertions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    insertions.sort(
        key=lambda item: item[0],
        reverse=True
    )

    for at, new_lines, label in insertions:

        lines[at:at] = new_lines

        logger.log(
            f"   ✨ Injected: {label}()"
        )

        stats["trace_injected"] += 1

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1
