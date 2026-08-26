#
# How far past a function's opening brace a trace is allowed to sit. The
# injector always writes it on the very next line; the slack absorbs hand
# edits and reformatting.
#
TRACE_SEARCH_WINDOW = 8


def find_trace_line(
    lines,
    brace_idx
):
    """Index of the trace at the top of this function body, or None."""

    begin = brace_idx + 1

    end = min(
        brace_idx + TRACE_SEARCH_WINDOW,
        len(lines)
    )

    for i in range(begin, end):

        if "ScopeTrace trace" in lines[i]:
            return i

    return None


def already_injected(
    lines,
    brace_idx
):

    return find_trace_line(
        lines,
        brace_idx
    ) is not None


def trace_block_end(
    lines,
    trace_idx
):
    """
    Index one past the last line of the trace block that starts at
    `trace_idx`, swallowing the blank line the injector leaves behind.
    """

    i = trace_idx + 1

    while i < len(lines):

        if ");" in lines[i]:
            i += 1
            break

        i += 1

    if (
        i < len(lines)
        and
        lines[i].strip() == ""
    ):
        i += 1

    return i


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
