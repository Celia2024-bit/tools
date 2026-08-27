from .constants import LEGACY_TRACE_PATTERN, SCOPE_TRACE
from .line_utils import (
    find_legacy_trace_line,
    find_open_brace_line,
    legacy_block_end,
    marker_of,
    payload_span
)
from .targets import (
    iter_target_functions,
    log_parse_problems,
    parse_translation_unit
)


def remove_trace_from_file(
    cpp_file,
    logger,
    stats,
    target_function="",
    target_base_class="",
    excluded_functions=None,
    include_dirs=None
):
    """
    With no function/base_class filter and nothing excluded, strip every
    trace in the file — the cheap line scan, which also catches traces the
    injector did not place. Any filter at all switches to the AST pass, which
    removes exactly the traces the matching inject rule would have added.
    """

    if excluded_functions is None:
        excluded_functions = set()

    targeted = bool(
        target_function
        or
        target_base_class
        or
        excluded_functions
    )

    if targeted:

        return _remove_targeted(
            cpp_file,
            logger,
            stats,
            target_function,
            target_base_class,
            excluded_functions,
            include_dirs
        )

    return _remove_all(
        cpp_file,
        logger,
        stats
    )


def _write_back(
    cpp_file,
    lines,
    logger,
    stats
):

    if not lines:

        logger.log(
            "   ✅ No changes required."
        )
        return

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["files_modified"] += 1


def _span_to_delete(
    lines,
    brace_idx
):
    """
    Half-open span of the trace at the top of this body, or None.

    Marker first, then the pre-marker layout. Trying the marker first matters:
    a marked line contains the legacy pattern too, so the order decides
    whether the blank separator goes with it.
    """

    span = payload_span(
        lines,
        brace_idx,
        SCOPE_TRACE
    )

    if span is not None:
        return span

    trace_idx = find_legacy_trace_line(
        lines,
        brace_idx
    )

    if trace_idx is None:
        return None

    return trace_idx, legacy_block_end(
        lines,
        trace_idx
    )


def _remove_targeted(
    cpp_file,
    logger,
    stats,
    target_function,
    target_base_class,
    excluded_functions,
    include_dirs
):

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

    deletions = []

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

        span = _span_to_delete(
            lines,
            brace_idx
        )

        if span is None:
            continue

        begin, end = span

        deletions.append(
            (
                begin,
                end,
                label
            )
        )

    if not deletions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # apply bottom-up so earlier indices stay valid
    #
    deletions.sort(
        key=lambda item: item[0],
        reverse=True
    )

    for begin, end, label in deletions:

        del lines[begin:end]

        logger.log(
            f"   ✨ Removed: {label}()"
        )

        stats["trace_removed"] += 1

    _write_back(
        cpp_file,
        lines,
        logger,
        stats
    )


def _remove_all(
    cpp_file,
    logger,
    stats
):

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    modified = False

    i = 0

    result = []

    while i < len(lines):

        name = marker_of(
            lines[i]
        )

        if name:

            #
            # One log line per payload, not per source line: a payload may
            # span several, each carrying the same marker.
            #
            end = i + 1

            while (
                end < len(lines)
                and
                marker_of(lines[end]) == name
            ):
                end += 1

            if (
                end < len(lines)
                and
                lines[end].strip() == ""
            ):
                end += 1

            logger.log(
                f"   ✨ Removed {name}"
            )

            stats["trace_removed"] += 1

            modified = True

            i = end

            continue

        if LEGACY_TRACE_PATTERN in lines[i]:

            logger.log(
                "   ✨ Removed ScopeTrace (unmarked)"
            )

            stats["trace_removed"] += 1

            modified = True

            i = legacy_block_end(
                lines,
                i
            )

            continue

        result.append(
            lines[i]
        )

        i += 1

    if not modified:

        logger.log(
            "   ✅ No changes required."
        )
        return

    _write_back(
        cpp_file,
        result,
        logger,
        stats
    )
