from .constants import LEGACY_TRACE_PATTERN, SCOPE_TRACE
from .line_utils import (
    find_legacy_trace_line,
    injected_span,
    is_include,
    legacy_block_end,
    marker_of,
    markers_in_span,
    orphaned_include_lines,
    payload_span
)
from .targets import (
    body_open_brace,
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
    include_dirs=None,
    payload_names=None
):
    """
    With no function/base_class filter and nothing excluded, strip every
    trace in the file — the cheap line scan, which also catches traces the
    injector did not place. Any filter at all switches to the AST pass, which
    removes exactly the traces the matching inject rule would have added.

    `payload_names` of None means every marker found, whether or not the
    config still defines a payload by that name. A list narrows it.
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
            include_dirs,
            payload_names
        )

    return _remove_all(
        cpp_file,
        logger,
        stats,
        payload_names
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


def _wanted(payload_names, name):

    return payload_names is None or name in payload_names


def _drop_orphaned_includes(
    lines,
    logger,
    stats
):
    """
    Delete the includes nothing in the file needs any more. Returns whether
    anything went.

    Runs after the payload lines are already out, since that is what decides
    which includes are still earning their place. An include the author wrote
    themselves carries no marker and is never touched.
    """

    orphans = orphaned_include_lines(lines)

    for i in reversed(orphans):

        logger.log(
            f"   ➖ Include: {lines[i].strip()}"
        )

        del lines[i]

        stats["includes_removed"] += 1

    return bool(orphans)


def _spans_to_delete(
    lines,
    brace_idx,
    payload_names
):
    """
    The spans to cut from the top of this body: one per payload, or a single
    span covering the lot when every payload there is wanted.

    Markers first, then the pre-marker layout. The order matters — a marked
    line contains the legacy pattern too, so trying markers first is what
    decides whether the blank separator goes with it.
    """

    begin, end = injected_span(
        lines,
        brace_idx
    )

    present = markers_in_span(
        lines,
        begin,
        end
    )

    if present:

        wanted = [
            name
            for name in present
            if _wanted(payload_names, name)
        ]

        if not wanted:
            return []

        #
        # Cutting the whole region in one go also takes the blank separator,
        # which no individual payload span may claim while others remain.
        #
        if len(wanted) == len(present):
            return [(begin, end)]

        return [
            payload_span(
                lines,
                brace_idx,
                name
            )
            for name in wanted
        ]

    if not _wanted(payload_names, SCOPE_TRACE):
        return []

    trace_idx = find_legacy_trace_line(
        lines,
        brace_idx
    )

    if trace_idx is None:
        return []

    return [
        (
            trace_idx,
            legacy_block_end(
                lines,
                trace_idx
            )
        )
    ]


def _remove_targeted(
    cpp_file,
    logger,
    stats,
    target_function,
    target_base_class,
    excluded_functions,
    include_dirs,
    payload_names
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
    labels = []

    for node, label in iter_target_functions(
        tu,
        target_function,
        target_base_class,
        excluded_functions,
        logger
    ):

        #
        # A one-line body needs no guard here: nothing was ever put in one, so
        # the span comes back empty and the function is passed over in silence.
        #
        brace_idx = body_open_brace(
            node,
            lines
        )

        if brace_idx is None:
            continue

        spans = _spans_to_delete(
            lines,
            brace_idx,
            payload_names
        )

        if not spans:
            continue

        deletions.extend(spans)
        labels.append(label)

    if not deletions:

        logger.log(
            "   ✅ No changes required."
        )
        return

    #
    # Bottom-up so earlier indices stay valid. The spans are disjoint, so
    # sorting the tuples is enough.
    #
    for begin, end in sorted(
        deletions,
        reverse=True
    ):
        del lines[begin:end]

    _drop_orphaned_includes(
        lines,
        logger,
        stats
    )

    #
    # One line per function, not per payload: the counter has always meant
    # "functions whose trace came out", and a function with three payloads
    # lost one trace, not three.
    #
    for label in labels:

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
    stats,
    payload_names
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

        #
        # A marked #include is ours too, but it is not a trace: whether it
        # goes depends on what is left after the payload lines are out, so it
        # is left to _drop_orphaned_includes below.
        #
        if (
            name
            and
            not is_include(lines[i])
            and
            _wanted(payload_names, name)
        ):

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

            #
            # Take the blank separator only when this was the last payload
            # standing. A payload left in place above or below still needs it.
            #
            if (
                end < len(lines)
                and
                lines[end].strip() == ""
                and
                (
                    end + 1 >= len(lines)
                    or
                    marker_of(lines[end + 1]) is None
                )
                and
                not (
                    result
                    and
                    marker_of(result[-1])
                )
            ):
                end += 1

            logger.log(
                f"   ✨ Removed {name}"
            )

            stats["trace_removed"] += 1

            modified = True

            i = end

            continue

        if (
            name is None
            and
            LEGACY_TRACE_PATTERN in lines[i]
            and
            _wanted(payload_names, SCOPE_TRACE)
        ):

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

    if _drop_orphaned_includes(
        result,
        logger,
        stats
    ):
        modified = True

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
