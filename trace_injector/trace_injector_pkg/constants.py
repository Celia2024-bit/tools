"""
What the injector writes, and therefore what the remover must be able to take
back out again.

Every injection kind declares all three halves in one place: `build` produces
the lines, `header` is the include those lines need, and the kind's name is what
the marker comment carries. Adding a kind means adding one entry to
INJECTION_KINDS — inject and remove both read from it, so the two cannot drift
apart. Remove is deliberately kind-blind: it strips every marker it finds,
whatever "inject_type" put it there.

`build` returns two lists, not one: what goes above the body and what goes
below it. Most kinds only prepend and return nothing for the second — but a
kind that *wraps* the body, like the try/catch "guard", has to write at both
ends, and there is no way to express that as a block at the top. The two halves
carry different markers so the remover can tell an opening from a closing.

Injected lines are found again by their marker comment, not by the C++ they
contain. Matching on the code was the old way and it could not tell an injected
`ScopeTrace trace(...)` from a hand-written one, so remove deleted both. The
marker is the tool's signature: no marker, not ours, left alone.
"""

DEFAULT_INJECT_TYPES = ["trace"]

#
# Appended to every line the injector writes. Kept in one piece so a search for
# it in a source tree finds every trace of this tool at once.
#
INJECT_MARKER = "// inject automatically"


def block_marker(kind):
    """The marker carried by each line of an injected block."""

    return f"{INJECT_MARKER}: {kind}"


def block_end_marker(kind):
    """
    The marker carried by the closing half of a block that wraps the body.

    Its own marker rather than block_marker's, because the two halves are not
    interchangeable: the closing half of a guard is `}` and the catch arms, and
    a whole-file scan that could not tell it from an opening would count one
    injection as two. None of the three suffixes is a suffix of another, which
    is what lets kind_of_line decide by endswith alone.
    """

    return f"{INJECT_MARKER}: end of {kind}"


def include_marker(kind):
    """
    The marker carried by an #include the injector added.

    Distinct from block_marker on purpose: an include is file-scoped and a
    block is function-scoped, so the two are added, counted and removed under
    different rules and must never be mistaken for each other.
    """

    return f"{INJECT_MARKER}: include for {kind}"


def mark_lines(lines, marker):
    """
    Append `marker` to every non-blank line of a block.

    Every line, not just the first: the ScopeTrace block spans five lines, and
    a marker on only one of them would leave the remover to work out where the
    block ends by counting brackets. Marked line by line, removal is a filter.

    Takes the marker rather than the kind because the caller knows which half of
    the block it is marking and this does not.
    """

    return [
        f"{line.rstrip()}  {marker}\n"
        if line.strip()
        else line
        for line in lines
    ]


def get_scope_trace_lines(func_name, param_names):
    """The ScopeTrace guard placed at the top of a function body."""

    return (
        [
            "    ScopeTrace trace(\n",
            "        __FILE__,\n",
            "        __LINE__,\n",
            f'        "{func_name}"\n',
            "    );\n",
            "\n"
        ],
        []
    )


def get_validate_params_lines(func_name, param_names):
    """
    The parameter check, plus the name table it reads.

    Empty for a function that takes no parameters: there is nothing to check,
    and `const char* __param_names[] = {}` does not compile.
    """

    if not param_names:
        return [], []

    names = ", ".join(
        f'"{name}"'
        for name in param_names
    )

    args = ", ".join(param_names)

    return (
        [
            f"    static const char* __param_names[] = {{ {names} }};\n",
            f'    validate_params("{func_name}", __param_names, {args});\n',
            "\n"
        ],
        []
    )


def get_try_catch_lines(func_name, param_names):
    """
    The try/catch that wraps a body it does not otherwise touch: `try {` above
    it, `}` and the catch arms below.

    The one kind that writes at both ends, which is the whole reason `build`
    returns a pair. Nothing about the body itself changes — not even its
    indentation, which is now one level shallower than the block it sits in.
    That is deliberate: this tool's promise is that remove gives you back the
    file you had, byte for byte, and reindenting would make every injection a
    diff across the whole function.

    `throw;` is not optional. Swallowing the exception would change what the
    program does, and in a function that returns something it would fall off the
    end of the body — which is undefined behaviour, not a compile error.

    The scope and the name are baked in as literals rather than read from
    __func__, so the log says `OrderMgr::SubmitOrder` and not `SubmitOrder`.
    className is empty for a free function and the namespace for one inside a
    namespace, which is as close to "which class" as either has.

    The trailing blank on the opening half is load-bearing: injected_block_end
    swallows exactly one blank after a run of marked lines, so the block has to
    bring its own or it eats one belonging to the body.
    """

    class_name, _, method = func_name.rpartition("::")

    return (
        [
            "    try\n",
            "    {\n",
            "\n"
        ],
        [
            "    }\n",
            "    catch (const std::exception& error)\n",
            "    {\n",
            f'        ErrorLogger::LogError("{class_name}", "{method}", '
            f'"std::exception", error.what());\n',
            "        throw;\n",
            "    }\n",
            "    catch (...)\n",
            "    {\n",
            f'        ErrorLogger::LogError("{class_name}", "{method}", '
            f'"unknown", "unrecognised exception");\n',
            "        throw;\n",
            "    }\n"
        ]
    )


#
# Order matters three times over: it is the order blocks are written in, so the
# log and the file read the same way; remove walks the run of blocks in file
# order regardless; and "guard" comes last so its `try` opens directly above the
# original body. That puts ScopeTrace and the parameter check *outside* the try,
# which is what you want — the trace object is then still alive while the catch
# runs, and its destructor logs the exit after it.
#
# The headers are named, not located. Where they are found is the project's
# `-I`, exactly as for every other header the sources include; ScopeTrace.h,
# ParameterCheck.h and ErrorLogger.h live in the util library and are maintained
# there.
#
INJECTION_KINDS = (
    (
        "trace",
        get_scope_trace_lines,
        "ScopeTrace.h"
    ),
    (
        "validate",
        get_validate_params_lines,
        "ParameterCheck.h"
    ),
    (
        "guard",
        get_try_catch_lines,
        "ErrorLogger.h"
    )
)


def injected_headers():
    """Every header this tool includes on the sources' behalf."""

    return tuple(
        header
        for _, _, header in INJECTION_KINDS
    )


def normalize_inject_types(inject_types):
    """
    A rule may say "trace", ["trace", "validate"], or nothing at all. Callers
    should not each re-handle that.
    """

    if inject_types is None:
        return list(DEFAULT_INJECT_TYPES)

    if isinstance(inject_types, str):
        return [inject_types]

    return list(inject_types)


def build_injected_blocks(
    func_name,
    param_names,
    inject_types=None
):
    """
    The (kind, opening lines, closing lines) triples to insert for one function,
    in INJECTION_KINDS order.

    A kind that produced nothing at either end is left out rather than reported
    as an empty block, which is what makes "so which includes does this file
    need" a question about what was written instead of about what the rule asked
    for.
    """

    wanted = normalize_inject_types(inject_types)

    blocks = []

    for kind, build, _ in INJECTION_KINDS:

        if kind not in wanted:
            continue

        top, tail = build(
            func_name,
            param_names
        )

        if top or tail:
            blocks.append(
                (
                    kind,
                    mark_lines(
                        top,
                        block_marker(kind)
                    ),
                    mark_lines(
                        tail,
                        block_end_marker(kind)
                    )
                )
            )

    return blocks


def kind_of_line(line):
    """Which injection kind wrote this line, or None if nothing did."""

    stripped = line.rstrip()

    for kind, _, _ in INJECTION_KINDS:

        if stripped.endswith(
            block_marker(kind)
        ):
            return kind

        if stripped.endswith(
            block_end_marker(kind)
        ):
            return kind

    return None


def is_block_end_line(line):
    """
    Is this the closing half of a block rather than the opening one?

    What tells a whole-file scan that the run it is looking at is the bottom of
    an injection it has already counted, and not an injection of its own.
    """

    stripped = line.rstrip()

    return any(
        stripped.endswith(
            block_end_marker(kind)
        )
        for kind, _, _ in INJECTION_KINDS
    )
