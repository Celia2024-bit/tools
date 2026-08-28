"""
Finding injected code again by reading lines, once the AST has said which
function to look at.

Nothing here knows or cares which inject_type wrote a block: a line either
carries the marker comment for one of the kinds in constants.INJECTION_KINDS or
it does not. That is what lets remove restore a function to its original state
without being told what was put there — and what keeps it off code the injector
never wrote.
"""

from .constants import kind_of_line

#
# How far past a function's opening brace an injected block is allowed to
# start. The injector always writes it on the very next line; the slack absorbs
# hand edits and reformatting.
#
INJECTION_SEARCH_WINDOW = 8


def is_injected_line(line):

    return kind_of_line(line) is not None


def injected_block_end(
    lines,
    begin
):
    """
    Index one past the injected block starting at `begin`, swallowing the blank
    line the injector leaves behind it.

    Every line of a block carries the marker, so the block ends where the
    marking stops — no counting brackets, no looking for the terminating `;`.
    That is what a per-line marker buys.
    """

    i = begin

    while (
        i < len(lines)
        and
        is_injected_line(lines[i])
    ):
        i += 1

    if (
        i < len(lines)
        and
        lines[i].strip() == ""
    ):
        i += 1

    return i


def injected_region_end(
    lines,
    begin
):
    """
    Index one past the whole *run* of injected blocks starting at `begin`.

    One function can carry several blocks at once — trace then validate — and
    stopping after the first is the bug this exists to prevent: the leftover
    block is invisible to already_injected(), so the next inject writes a
    second copy and `__param_names` ends up declared twice in one scope.
    """

    i = begin

    while (
        i < len(lines)
        and
        is_injected_line(lines[i])
    ):
        i = injected_block_end(
            lines,
            i
        )

    return i


def injected_kinds(
    lines,
    begin,
    end
):
    """The kinds present in lines[begin:end], in the order they appear."""

    found = []

    for line in lines[begin:end]:

        kind = kind_of_line(line)

        if kind and kind not in found:
            found.append(kind)

    return found


def find_injected_line(
    lines,
    brace_idx
):
    """Index of the first injected line at the top of this body, or None."""

    begin = brace_idx + 1

    end = min(
        brace_idx + INJECTION_SEARCH_WINDOW,
        len(lines)
    )

    for i in range(begin, end):

        if is_injected_line(lines[i]):
            return i

    return None


def already_injected(
    lines,
    brace_idx
):
    """
    Any injected block counts, not only a trace.

    A function holding a validate block but no trace is still injected. Calling
    it clean and writing a fresh block above it is how you get two
    `__param_names` declarations in one scope and a file that will not compile.
    """

    return find_injected_line(
        lines,
        brace_idx
    ) is not None


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
