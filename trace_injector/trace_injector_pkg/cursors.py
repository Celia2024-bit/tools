"""
Reading a cursor's kind without trusting the bindings to know every one.

`cursor.kind` looks like an attribute and is really a lookup in a table the
python bindings carry, hand-written per release. libclang is versioned
separately and hands back ids the bindings have never heard of, at which point
the bindings raise:

    ValueError: Unknown template argument kind 280

That is a real crash on real code — anything including <string> reaches one — and
it happens on a cursor the tool was going to skip anyway. A kind nobody can name
is a kind that matches none of the tuples here, so None is exactly right and the
traversal carries on.

Every read of a cursor's kind goes through kind_of. A bare `.kind` anywhere is a
crash waiting for the next clang release.
"""


def kind_of(cursor):
    """This cursor's kind, or None when the bindings cannot name it."""

    try:
        return cursor.kind

    except ValueError:
        return None
