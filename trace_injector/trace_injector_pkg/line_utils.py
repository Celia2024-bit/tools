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


def is_include(line):
    return line.lstrip().startswith("#include")


def has_include(lines, directive):
    """
    Whether this exact `#include ...` is already in the file, whoever put it
    there. `directive` carries its own closing quote or bracket, so it cannot
    match "Trace.h" against "Trace.hpp".
    """

    return any(
        line.strip().startswith(directive)
        for line in lines
    )


def include_insert_point(lines):
    """
    Where a new #include goes: right after the last one already there, so it
    joins the block instead of jumping the file's own header.

    With no includes at all, after whatever the file opens with — a comment
    block, a #pragma — and before the first line of code. No blank line is
    added either way: the include sits flush against its neighbours, which is
    what lets removal put the file back byte for byte.
    """

    last = None

    for i, line in enumerate(lines):

        if is_include(line):
            last = i

    if last is not None:
        return last + 1

    i = 0
    in_comment = False

    while i < len(lines):

        text = lines[i].strip()

        if in_comment:

            if "*/" in text:
                in_comment = False

            i += 1
            continue

        if text.startswith("/*"):
            in_comment = "*/" not in text
            i += 1
            continue

        if (
            text == ""
            or
            text.startswith("//")
            or
            text.startswith("#pragma")
        ):
            i += 1
            continue

        break

    return i


def orphaned_include_lines(lines):
    """
    The marked #include lines whose payload has nothing left in this file.

    An include is only worth keeping while something needs it, and after a
    removal pass nothing might. Counted across the whole file rather than per
    function, since one include serves every payload line in it. A marked
    include is itself a marker, so it does not count as its own reason to stay.
    """

    body_markers = set()

    for line in lines:

        name = marker_of(line)

        if name and not is_include(line):
            body_markers.add(name)

    return [
        i
        for i, line in enumerate(lines)
        if is_include(line)
        and marker_of(line)
        and marker_of(line) not in body_markers
    ]


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
