"""
Finding libclang before anything asks the bindings to parse.

The clang python bindings load the shared library through the OS loader, which
does not look inside site-packages — so `pip install libclang` puts the library
somewhere the bindings cannot see, and the failure is a LibclangError at the
first parse rather than at import. Searching here is the difference between
"run the tool" and "run the tool after reading the README".

Import order matters: this has to run before any translation unit is parsed.
Both entry points call it first thing, and nothing else needs to know.
"""

import os
import sys

from pathlib import Path

#
# Set TRACE_INJECTOR_LIBCLANG to skip the search entirely, which is also how a
# tree pins a particular clang version.
#
LIBRARY_ENV_VAR = "TRACE_INJECTOR_LIBCLANG"


def library_name():

    names = {
        "win32": "libclang.dll",
        "darwin": "libclang.dylib"
    }

    return names.get(sys.platform, "libclang.so")


def candidates():
    """
    Where libclang tends to be, best guess first: the bindings' own bundled
    copy, then this interpreter's prefix, then the usual system locations.
    """

    import clang

    name = library_name()

    yield Path(clang.__file__).parent / "native" / name

    for base in (
        Path(sys.prefix),
        Path(sys.prefix) / "Library",
        Path("C:/Program Files/LLVM"),
        Path("/usr/lib/llvm-14"),
        Path("/usr/lib"),
        Path("/usr/local/lib"),
        Path("/opt/homebrew/lib")
    ):
        yield base / "bin" / name
        yield base / "lib" / name
        yield base / name


def configure():
    """
    Point the bindings at a libclang they can load. Returns the path in use, or
    None when the default loader already worked and nothing had to be set.

    Calling this twice is safe: the second call finds the loader working and
    returns None without touching the configuration.
    """

    from clang import cindex

    explicit = os.environ.get(LIBRARY_ENV_VAR, "")

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

        cindex.Config.set_library_file(str(candidate))

        try:
            cindex.Index.create()
            return str(candidate)

        except cindex.LibclangError:
            #
            # A file by the right name that will not load — a stub, or built
            # for another architecture. Clearing the flag is what lets
            # set_library_file be called again for the next candidate.
            #
            cindex.Config.loaded = False

    raise SystemExit(
        f"Could not load libclang. Install it (pip install libclang) or set "
        f"{LIBRARY_ENV_VAR} to the shared library."
    )
