"""
Finding libclang before anything asks clang to parse.

The clang python bindings load the shared library through the OS loader, which
does not look inside site-packages — so `pip install libclang` puts the file on
disk and the import still fails. Locating it here is the difference between
"run this tool" and "run this tool after reading the README".

Nothing in the package calls a clang function until configure() has run, so
cli.py calls it once at startup. Import order does not matter: the bindings
resolve the library lazily, on the first Index.create().
"""

import os
import sys
from pathlib import Path

ENV_VAR = "TRACE_INJECTOR_LIBCLANG"

#
# Where a working install actually puts it, most likely first. The pip wheel is
# checked ahead of a system LLVM because it is the one this tool's own
# instructions tell you to install.
#
SEARCH_ROOTS = (
    Path(sys.prefix),
    Path(sys.prefix) / "Library",
    Path("C:/Program Files/LLVM"),
    Path("/usr/lib/llvm-14"),
    Path("/usr/lib"),
    Path("/usr/local/lib"),
    Path("/opt/homebrew/lib")
)

LIBRARY_NAMES = {
    "win32": "libclang.dll",
    "darwin": "libclang.dylib"
}


def library_name():

    return LIBRARY_NAMES.get(
        sys.platform,
        "libclang.so"
    )


def candidates():

    name = library_name()

    try:
        import clang
    except ImportError:
        pass
    else:
        yield Path(clang.__file__).parent / "native" / name

    for base in SEARCH_ROOTS:

        yield base / "bin" / name
        yield base / "lib" / name
        yield base / name


def configure():
    """
    Point the bindings at a libclang that loads. Returns the path in use, None
    if the OS loader already found one by itself.

    Candidates are tried by loading them, not by existing: a file of the right
    name whose own dependencies are missing fails at Index.create(), and giving
    up there would report "not found" while staring at it.
    """

    from clang import cindex

    explicit = os.environ.get(
        ENV_VAR,
        ""
    )

    #
    # An explicit path is used as given and not verified. If it is wrong the
    # caller wants clang's own error about the file they named, not this
    # module's search results.
    #
    if explicit:

        cindex.Config.set_library_file(explicit)

        return explicit

    try:
        cindex.Index.create()
        return None
    except cindex.LibclangError:
        pass

    for candidate in candidates():

        if not candidate.is_file():
            continue

        cindex.Config.set_library_file(
            str(candidate)
        )

        try:
            cindex.Index.create()
            return str(candidate)
        except cindex.LibclangError:
            #
            # Reset, or the bindings keep the failed path and every later
            # attempt reports that one instead of the candidate being tried.
            #
            cindex.Config.loaded = False

    #
    # Only the directories that exist. The candidate list spans every platform,
    # so printing all of it means telling a Windows user we looked in /usr/lib —
    # which reads as a bug in the tool rather than a missing install.
    #
    looked_in = []

    for candidate in candidates():

        parent = str(candidate.parent)

        if candidate.parent.is_dir() and parent not in looked_in:
            looked_in.append(parent)

    raise SystemExit(
        f"Could not find {library_name()}. Install it with "
        f"`pip install libclang`, or set {ENV_VAR} to the shared library.\n"
        +
        "\n".join(
            f"  looked in: {parent}"
            for parent in looked_in
        )
    )
