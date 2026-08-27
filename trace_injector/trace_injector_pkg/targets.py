"""
Shared target selection: parsing a translation unit and deciding which
function definitions a rule selects. Inject and remove use the same pass, so
whatever inject can put in, remove can take back out.
"""

import os

from clang import cindex

from .class_hierarchy import is_or_derives_from, owning_class, qualified_name
from .file_discovery import match_function

MAX_REPORTED_DIAGNOSTICS = 3

#
# Fatal only. See log_parse_problems for why lowering this cries wolf.
#
MIN_REPORTED_SEVERITY = cindex.Diagnostic.Fatal

FUNCTION_KINDS = (
    cindex.CursorKind.CXX_METHOD,
    cindex.CursorKind.FUNCTION_DECL
)


def build_clang_args(include_dirs):

    args = [
        "-x",
        "c++",
        "-std=c++17"
    ]

    for include_dir in include_dirs or []:
        args.append(
            f"-I{include_dir}"
        )

    return args


def parse_translation_unit(
    cpp_file,
    include_dirs
):

    index = cindex.Index.create()

    return index.parse(
        str(cpp_file),
        args=build_clang_args(include_dirs)
    )


def log_parse_problems(tu, logger):
    """
    Only worth calling when a base_class filter is active: a header clang
    cannot read leaves the derived class looking base-less, so the rule
    silently matches nothing. A silent miss is worse than a noisy warning.

    Fatal only, deliberately. A missing #include is fatal; ordinary semantic
    errors are not, and they do not stop the hierarchy from resolving. The
    common one is "unknown type name 'ScopeTrace'" on a second run, because
    the injector writes the trace without adding its header — reporting that
    would train the reader to ignore the warning that matters.
    """

    reported = 0

    for diagnostic in tu.diagnostics:

        if diagnostic.severity < MIN_REPORTED_SEVERITY:
            continue

        if reported >= MAX_REPORTED_DIAGNOSTICS:

            logger.log(
                "   ⚠️  ... more parse errors suppressed"
            )
            break

        logger.log(
            f"   ⚠️  Parse error: {diagnostic.spelling}"
        )

        reported += 1

    if reported:

        logger.log(
            "   ⚠️  Base-class matching may be incomplete — check "
            "\"include_dirs\" in the config."
        )


def _same_path(left, right):

    return os.path.normcase(
        os.path.abspath(left)
    ) == os.path.normcase(
        os.path.abspath(right)
    )


def in_main_file(node, tu):
    """
    Whether the node is defined in the file being rewritten rather than in
    something it includes.

    Not optional. The walk covers the whole translation unit — every header,
    including the system ones — while the caller indexes into the .cpp's own
    line array. A function defined inline in a header would otherwise have
    its payload placed at the header's line number inside the .cpp, landing
    in an unrelated function under a label naming the header's one.
    """

    location = node.location

    if location is None or location.file is None:
        return False

    return _same_path(
        location.file.name,
        tu.spelling
    )


def iter_target_functions(
    tu,
    target_function,
    target_base_class,
    excluded_functions,
    logger
):
    """
    Yield (node, label) for every function definition the rule selects.

    `label` is the fully qualified name, so overrides sharing a method name
    stay distinguishable in the log. Exclusions are reported here rather than
    by each caller, since the message is the same either way.
    """

    for node in tu.cursor.walk_preorder():

        if node.kind not in FUNCTION_KINDS:
            continue

        if not in_main_file(node, tu):
            continue

        if not node.is_definition():
            continue

        if not match_function(
            node.spelling,
            target_function
        ):
            continue

        if target_base_class and not is_or_derives_from(
            owning_class(node),
            target_base_class
        ):
            continue

        label = qualified_name(node)

        if node.spelling in excluded_functions:

            logger.log(
                f"   🚫 Excluded: {label}()"
            )
            continue

        yield node, label
