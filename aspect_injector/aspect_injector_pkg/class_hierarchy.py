from clang import cindex


CLASS_KINDS = (
    cindex.CursorKind.CLASS_DECL,
    cindex.CursorKind.STRUCT_DECL,
    cindex.CursorKind.CLASS_TEMPLATE,
    cindex.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION
)


def owning_class(method_node):
    """The class/struct a method belongs to, or None for free functions."""

    parent = method_node.semantic_parent

    if parent is None:
        return None

    if parent.kind not in CLASS_KINDS:
        return None

    return parent


def qualified_name(cursor):
    """
    Fully qualified name of any declaration, walking out through enclosing
    classes and namespaces — "AlphaStrategy" for a class, and
    "trading::AlphaStrategy::Run" for a method of one.
    """

    parts = [
        cursor.spelling
    ]

    parent = cursor.semantic_parent

    while parent is not None:

        if parent.kind not in CLASS_KINDS + (
            cindex.CursorKind.NAMESPACE,
        ):
            break

        if parent.spelling:
            parts.append(parent.spelling)

        parent = parent.semantic_parent

    parts.reverse()

    return "::".join(parts)


def _name_matches(class_cursor, requested_name):
    """
    Config may name the base class either unqualified ("A") or fully
    qualified ("ns::A") — accept both.
    """

    if class_cursor.spelling == requested_name:
        return True

    return qualified_name(class_cursor) == requested_name


def _direct_bases(class_cursor):

    definition = class_cursor.get_definition() or class_cursor

    for child in definition.get_children():

        if child.kind != cindex.CursorKind.CXX_BASE_SPECIFIER:
            continue

        base = child.type.get_declaration()

        if base is None:
            continue

        if base.kind == cindex.CursorKind.NO_DECL_FOUND:
            continue

        yield base


def is_or_derives_from(class_cursor, base_name):
    """
    True if `class_cursor` IS `base_name` or inherits from it at any depth.

    is-a semantics on purpose: when you are hunting for who calls a virtual
    function, the base class's own implementation is a candidate too.
    """

    if class_cursor is None:
        return False

    if not base_name:
        return False

    pending = [
        class_cursor
    ]

    seen = set()

    while pending:

        current = pending.pop()

        key = current.get_usr() or qualified_name(current)

        if key in seen:
            continue

        seen.add(key)

        if _name_matches(current, base_name):
            return True

        pending.extend(
            _direct_bases(current)
        )

    return False
