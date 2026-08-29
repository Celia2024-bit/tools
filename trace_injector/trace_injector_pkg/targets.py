"""
Shared target selection: parsing a translation unit and deciding which
function definitions a rule selects. Inject and remove use the same pass, so
whatever inject can put in, remove can take back out.
"""

from clang import cindex

from .class_hierarchy import is_or_derives_from, owning_class, qualified_name
from .injection_rules import injected_headers
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


def _is_our_header(diagnostic):
    """Is this diagnostic about a header the injector added itself?"""

    return any(
        f"'{header}'" in diagnostic.spelling
        for header in injected_headers()
    )


def log_parse_problems(tu, logger):
    """
    Only worth calling when a base_class filter is active: a header clang
    cannot read leaves the derived class looking base-less, so the rule
    silently matches nothing. A silent miss is worse than a noisy warning.

    Fatal only, deliberately. A missing #include is fatal; ordinary semantic
    errors are not, and they do not stop the hierarchy from resolving. Reporting
    those would train the reader to ignore the warning that matters.

    One fatal is filtered out all the same: the injector's own header, on a
    rerun over an already-injected tree whose `-I` does not cover ScopeTrace.h
    yet. It says nothing about base-class matching — the include is written
    below the file's own, so everything the hierarchy needs has already been
    read by the time clang gets there — and it would fire on every file.
    """

    reported = 0

    for diagnostic in tu.diagnostics:

        if diagnostic.severity < MIN_REPORTED_SEVERITY:
            continue

        if _is_our_header(diagnostic):
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
        try:
            kind = node.kind
        except ValueError:
            continue
        if kind not in FUNCTION_KINDS:
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

def get_function_param_names(node):
    """遍历 AST 提取函数的参数变量名"""
    params = []
    for child in node.get_children():
        if child.kind == cindex.CursorKind.PARM_DECL:
            param_name = child.spelling
            if param_name:  # 过滤匿名参数
                params.append(param_name)
    return params