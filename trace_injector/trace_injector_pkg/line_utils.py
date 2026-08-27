from .constants import LEGACY_TRACE_PATTERN, MARKER_PREFIX

#
# How far past a function's opening brace a legacy (unmarked) trace is allowed
# to sit. Marked payloads need no such window — the marker itself says which
# lines are ours, so injected_span reads the run instead of guessing at it.
#
TRACE_SEARCH_WINDOW = 8


def marker_of(line):
    """The payload name this line was injected for, or None if it is not ours."""

    at = line.find(MARKER_PREFIX)

    if at == -1:
        return None

    return line[at + len(MARKER_PREFIX):].strip() or None


def injected_span(
    lines,
    brace_idx
):
    """
    Half-open span of the injected region at the top of a function body: the
    run of marked lines following the opening brace, blank lines between them
    included, plus the single blank line the injector leaves after the last
    one.

    Returns an empty span when nothing of ours is there. The span starts at
    the first marked line, not at the brace, so a blank line the author put
    before the payloads is left alone.
    """

    first = None
    last = None

    i = brace_idx + 1

    while i < len(lines):

        if marker_of(lines[i]):

            if first is None:
                first = i

            last = i

        elif lines[i].strip() != "":
            break

        i += 1

    if first is None:
        return brace_idx + 1, brace_idx + 1

    end = last + 1

    if (
        end < len(lines)
        and
        lines[end].strip() == ""
    ):
        end += 1

    return first, end


def markers_in_span(
    lines,
    begin,
    end
):
    """
    The payload names present in a span, in the order they appear and without
    repeats. A payload spanning several lines marks each of them.
    """

    names = []

    for i in range(begin, end):

        name = marker_of(lines[i])

        if name and name not in names:
            names.append(name)

    return names


def insert_point(
    lines,
    brace_idx
):
    """
    Where a new payload goes, as (index, needs_separator): after the payloads
    already at the top of this body, before the blank line separating them
    from the code.

    `needs_separator` says whether the caller has to append that blank line
    itself, which it does whenever there is not one there already.
    """

    begin, end = injected_span(
        lines,
        brace_idx
    )

    if begin == end:
        return brace_idx + 1, True

    if lines[end - 1].strip() == "":
        return end - 1, False

    return end, True


def payload_span(
    lines,
    brace_idx,
    marker
):
    """
    Half-open span of the lines one payload contributed to this body, or None
    if that payload is not present.

    The trailing blank separator is swallowed only when this payload is the
    last one in the region — otherwise the blank belongs to whatever follows.
    """

    begin, end = injected_span(
        lines,
        brace_idx
    )

    mine = [
        i
        for i in range(begin, end)
        if marker_of(lines[i]) == marker
    ]

    if not mine:
        return None

    stop = mine[-1] + 1

    if all(
        lines[i].strip() == ""
        for i in range(stop, end)
    ):
        stop = end

    return mine[0], stop


def already_injected(
    lines,
    brace_idx,
    marker
):

    return payload_span(
        lines,
        brace_idx,
        marker
    ) is not None


def find_legacy_trace_line(
    lines,
    brace_idx
):
    """
    Index of an unmarked trace at the top of this function body, or None.

    Only for traces written before markers existed. A marked line matches
    LEGACY_TRACE_PATTERN too, so it is skipped here explicitly rather than
    counted twice.
    """

    begin = brace_idx + 1

    end = min(
        brace_idx + TRACE_SEARCH_WINDOW,
        len(lines)
    )

    for i in range(begin, end):

        if marker_of(lines[i]):
            continue

        if LEGACY_TRACE_PATTERN in lines[i]:
            return i

    return None


def legacy_block_end(
    lines,
    trace_idx
):
    """
    Index one past the last line of the legacy trace block that starts at
    `trace_idx`, swallowing the blank line the old injector left behind.
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
