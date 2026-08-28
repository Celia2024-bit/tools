"""
The `#include` the injected code needs, added on the way in and taken away
again on the way out.

Two things make this more than a line of text.

An include is file-scoped while the blocks are function-scoped, so it can only
go once the last block of its kind is gone: a remove rule naming one function
out of five has to leave the include in place for the other four. And a kind can
be asked for and produce nothing — "validate" meeting a function with no
parameters — so which include a file needs follows from what was written into
it, never from what the rule asked for. Getting that second one wrong drags
Types.h into a translation unit that has no use for it.

Nothing here computes a path. The headers are named the way the sources name
their own headers and found the same way, through the project's `-I`.
"""

import re

from .constants import (
    INJECTION_KINDS,
    include_marker,
    kind_of_line
)

INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*[<"]([^>"]+)[>"]'
)

DIRECTIVE_RE = re.compile(
    r'^\s*#\s*(\w+)'
)


def _directive(line):
    """The preprocessor directive this line opens, or "" if it is not one."""

    match = DIRECTIVE_RE.match(line)

    return match.group(1) if match else ""


def _after_leading_comments(lines):
    """
    Index of the first line that is neither blank nor part of the file's
    opening comment. Where the include goes in a file that has none of its own.
    """

    i = 0
    in_block = False

    while i < len(lines):

        stripped = lines[i].strip()

        if in_block:

            if "*/" in stripped:
                in_block = False

            i += 1
            continue

        if not stripped or stripped.startswith("//"):
            i += 1
            continue

        if stripped.startswith("/*"):
            in_block = "*/" not in stripped[2:]
            i += 1
            continue

        break

    return i


def find_include_slot(lines):
    """
    Index to insert at: just after the file's last unconditional #include.

    Last, so it lands after the file's own header and after anything that has to
    come first. Unconditional, because the last #include in a file is often
    inside `#if defined(_WIN32)` — appending to that block would make an
    include the injected code always needs depend on the platform.
    """

    depth = 0
    slot = None

    for i, line in enumerate(lines):

        directive = _directive(line)

        if directive.startswith("if"):
            depth += 1

        elif directive == "endif":
            depth = max(0, depth - 1)

        elif directive == "include" and depth == 0:
            slot = i + 1

    if slot is not None:
        return slot

    return _after_leading_comments(lines)


def included_headers(lines):
    """
    The header names this file already includes, at any depth and however
    written: "ScopeTrace.h" and "util/ScopeTrace.h" both count as having it.
    What matters is that the name already resolves for this translation unit.
    """

    names = set()

    for line in lines:

        match = INCLUDE_RE.match(line)

        if match:
            names.add(
                match.group(1).replace("\\", "/").rsplit("/", 1)[-1]
            )

    return names


def add_includes(
    lines,
    kinds
):
    """
    Add the include each of `kinds` needs, unless the file has it already.

    Returns (lines, added header names). An include that is already there is
    left alone whether the injector wrote it or a person did — a second copy
    would compile, but the remover would then have to decide which one is safe
    to delete.
    """

    present = included_headers(lines)

    new_lines = []
    added = []

    for kind, _, header in INJECTION_KINDS:

        if kind not in kinds or header in present:
            continue

        new_lines.append(
            f'#include "{header}"  {include_marker(kind)}\n'
        )

        added.append(header)

    if not new_lines:
        return lines, added

    slot = find_include_slot(lines)

    return (
        lines[:slot] + new_lines + lines[slot:],
        added
    )


def drop_orphan_includes(lines):
    """
    Delete each include of ours whose kind has no block left anywhere in the
    file. Returns (lines, dropped header names).

    Counted rather than paired with whatever block triggered the removal: the
    include serves the whole file, so the question is never "was a block
    removed" but "is there still one that needs this".

    An include nobody wrote a marker on is not ours and is not touched, which is
    the whole point of marking them.
    """

    live = {
        kind_of_line(line)
        for line in lines
    }

    orphans = {
        include_marker(kind): header
        for kind, _, header in INJECTION_KINDS
        if kind not in live
    }

    kept = []
    dropped = []

    for line in lines:

        stripped = line.rstrip()

        header = next(
            (
                orphans[marker]
                for marker in orphans
                if stripped.endswith(marker)
            ),
            None
        )

        if header:
            dropped.append(header)
            continue

        kept.append(line)

    return kept, dropped
