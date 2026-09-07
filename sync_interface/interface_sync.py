#!/usr/bin/env python3

import argparse
from pathlib import Path

from clang import cindex

from logger import Logger
from libclang import configure as configure_libclang

def cleanup_old_logs():

    current_dir = Path.cwd()

    for log_file in current_dir.glob("*.log"):

        try:

            log_file.unlink()

            print(
                f"Removed old log: {log_file.name}"
            )

        except Exception as ex:

            print(
                f"Failed to remove "
                f"{log_file}: {ex}"
            )


def build_signature(node):

    params = []

    for arg in node.get_arguments():

        params.append(
            f"{arg.type.spelling} {arg.spelling}"
        )

    return (
        f"{node.result_type.spelling} "
        f"{node.spelling}"
        f"({', '.join(params)})"
    )


def extract_interface(
    header_file,
    clang_args
):

    index = cindex.Index.create()

    tu = index.parse(
        header_file,
        args=clang_args
    )

    result = {}

    for node in tu.cursor.walk_preorder():

        if node.kind != cindex.CursorKind.CXX_METHOD:
            continue

        try:
            is_pure = (
                node.is_pure_virtual_method()
            )
        except Exception:
            is_pure = False

        if not is_pure:
            continue

        result[node.spelling] = {

            "name":
                node.spelling,

            "signature":
                build_signature(node),

            "return":
                node.result_type.spelling,

            "params":
                [
                    arg.type.spelling
                    for arg in node.get_arguments()
                ],

            #
            # Kept separate from "params" on purpose: "params" (types only)
            # is what compare_interfaces() diffs to decide whether a
            # signature changed, and a parameter name is not part of a C++
            # signature — "OnData(int id)" and "OnData(int x)" are the same
            # override. Folding names in there would make a purely cosmetic
            # rename look like a breaking change. This field exists only so
            # build_cpp_stub() can write a readable stub; a header that
            # doesn't name a parameter leaves the matching entry as "".
            #
            "param_names":
                [
                    arg.spelling
                    for arg in node.get_arguments()
                ]
        }

    return result


def compare_interfaces(
    old_api,
    new_api
):

    changes = {
        "deleted": [],
        "changed": [],
        "added": []
    }

    old_names = set(old_api.keys())
    new_names = set(new_api.keys())

    for name in sorted(
        old_names - new_names
    ):
        changes["deleted"].append(
            old_api[name]
        )

    for name in sorted(
        new_names - old_names
    ):
        changes["added"].append(
            new_api[name]
        )

    for name in sorted(
        old_names & new_names
    ):

        old_item = old_api[name]
        new_item = new_api[name]

        if (
            old_item["return"]
            !=
            new_item["return"]
        ) or (
            old_item["params"]
            !=
            new_item["params"]
        ):

            changes["changed"].append({

                "old":
                    old_item,

                "new":
                    new_item
            })

    return changes


def is_derived_from(
    class_cursor,
    interface_name
):

    for child in class_cursor.get_children():

        if (
            child.kind
            ==
            cindex.CursorKind.CXX_BASE_SPECIFIER
        ):

            if (
                child.spelling
                ==
                interface_name
            ):
                return True

    return False


def contains_derived_class(
    tu,
    interface_name
):

    for node in tu.cursor.walk_preorder():

        if (
            node.kind
            ==
            cindex.CursorKind.CLASS_DECL
        ):

            if is_derived_from(
                node,
                interface_name
            ):
                return True

    return False


def find_derived_class_name(
    tu,
    interface_name
):
    """
    The name of the class in this header that derives from interface_name.

    Only used once we already know (via contains_derived_class) that there is
    one — it exists so the .cpp stub can be qualified as "ClassName::Method",
    not because the header could plausibly have none.
    """

    for node in tu.cursor.walk_preorder():

        if (
            node.kind
            ==
            cindex.CursorKind.CLASS_DECL
        ):

            if is_derived_from(
                node,
                interface_name
            ):
                return node.spelling

    return None


def remove_override_lines(
    lines,
    tu,
    target_names
):

    modified = False

    for node in tu.cursor.walk_preorder():

        if (
            node.kind
            !=
            cindex.CursorKind.CXX_METHOD
        ):
            continue

        if node.spelling not in target_names:
            continue

        for token in node.get_tokens():

            if token.spelling != "override":
                continue

            line_no = token.location.line

            idx = line_no - 1

            original = lines[idx]

            updated = (
                original
                .replace(" override", "")
                .replace("override ", "")
            )

            if updated != original:

                lines[idx] = updated

                modified = True

    return modified


def append_stub(
    lines,
    signature
):

    func_name = (
        signature
        .split("(")[0]
        .split()[-1]
    )

    #
    # prevent duplicate stub
    #
    def append_stub(
        lines,
        signature
    ):

        stub_line = (
            f"    {signature} override;"
        )

        for line in lines:

            if (
                line.strip()
                ==
                stub_line.strip()
            ):
                return False


    insert_pos = None

    for i in range(
        len(lines) - 1,
        -1,
        -1
    ):

        if lines[i].strip() == "};":

            insert_pos = i
            break

    if insert_pos is None:
        return False

    lines.insert(
        insert_pos,
        f"    {signature} override;\n"
    )

    return True


def find_cpp_for_header(header_path):
    """
    The .cpp this header's class is implemented in, by the project's own
    naming convention: same stem, same directory. None if it doesn't exist —
    the caller decides what to do about that, this just looks.
    """

    candidate = header_path.with_suffix(".cpp")

    if candidate.is_file():
        return candidate

    return None


def has_cpp_implementation(
    tu,
    class_name,
    method_name,
    param_types
):
    """
    True if class_name::method_name(param_types...) — this exact overload,
    not just any method with this name — is already *defined* somewhere in
    this translation unit.

    Definition, not declaration: a stub only needs adding once, and checking
    is_definition() is what stops a second run from writing the same empty
    body in on top of one a person has since filled in.

    Matching on parameters as well as name is not optional: "OnData(int)"
    changing to "OnData(int, double)" is still named "OnData" either way, so
    a name-only check finds the old overload's body and wrongly concludes
    the new one is already implemented too — the new stub never gets
    written, and the file is left not actually compiling against the new
    interface.
    """

    for node in tu.cursor.walk_preorder():

        if node.kind != cindex.CursorKind.CXX_METHOD:
            continue

        if node.spelling != method_name:
            continue

        if not node.is_definition():
            continue

        parent = node.semantic_parent

        if parent is None:
            continue

        if parent.spelling != class_name:
            continue

        existing_params = [
            arg.type.spelling
            for arg in node.get_arguments()
        ]

        if existing_params != param_types:
            continue

        return True

    return False


def build_cpp_stub(
    class_name,
    item
):
    """
    An empty out-of-line definition for one interface method, in the shape
    "ReturnType ClassName::Method(Type name, ...) { }" — enough to satisfy
    the linker, nothing about behaviour.

    Parameter names come from the interface header when it has them ("int
    err_code" reads a lot better than a bare "int" once someone opens this
    file to fill it in) and fall back to the bare type when the header
    itself left a parameter unnamed — never invented.
    """

    return_type = item["return"]
    method_name = item["name"]

    param_types = item["params"]
    param_names = item.get("param_names", [])

    parts = []

    for i, param_type in enumerate(param_types):

        name = (
            param_names[i]
            if i < len(param_names)
            else ""
        )

        if name:
            parts.append(f"{param_type} {name}")
        else:
            parts.append(param_type)

    params = ", ".join(parts)

    return [
        f"{return_type} {class_name}::{method_name}({params})\n",
        "{\n",
        "    // TODO: implement\n",
        "}\n",
        "\n"
    ]


def sync_cpp_implementation(
    cpp_file,
    class_name,
    changes,
    clang_args,
    logger,
    stats
):
    """
    Append a stub definition for every added or changed interface method that
    this .cpp doesn't already implement.

    Deleted methods are deliberately absent here: the header keeps the old
    declaration (minus "override"), so the existing .cpp definition still
    matches it and still compiles — there is nothing to add or remove on the
    .cpp side for a deletion, consistent with this tool never deleting a
    person's own code.
    """

    if cpp_file is None:

        logger.log(
            f"   ⚠️  No matching .cpp file for {class_name} — "
            "skipping implementation stub(s)."
        )

        return

    index = cindex.Index.create()

    tu = index.parse(
        str(cpp_file),
        args=clang_args
    )

    targets = (
        [item["new"] for item in changes["changed"]]
        +
        changes["added"]
    )

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    added_any = False

    for item in targets:

        if has_cpp_implementation(
            tu,
            class_name,
            item["name"],
            item["params"]
        ):
            continue

        if lines and lines[-1].strip():
            lines.append("\n")

        lines.extend(
            build_cpp_stub(
                class_name,
                item
            )
        )

        added_any = True

        logger.log(
            f"   ✨ Added stub implementation: {class_name}::{item['name']}()"
        )

        stats["cpp_stubs_added"] += 1

    if not added_any:
        return

    cpp_file.write_text(
        "".join(lines),
        encoding="utf-8"
    )

    stats["cpp_files_modified"] += 1


def process_file(
    file_path,
    interface_name,
    changes,
    logger,
    stats,
    clang_args
):

    index = cindex.Index.create()

    tu = index.parse(
        file_path,
        args=clang_args
    )

    if not contains_derived_class(
        tu,
        interface_name
    ):
        return

    class_name = find_derived_class_name(
        tu,
        interface_name
    )

    stats["derived_classes"] += 1

    logger.log()
    logger.log(
        f"⚙️ Inspecting Derived Class file: {file_path}..."
    )

    lines = Path(
        file_path
    ).read_text(
        encoding="utf-8"
    ).splitlines(True)

    modified = False

    #
    # deleted
    #
    deleted_names = [
        x["name"]
        for x in changes["deleted"]
    ]

    if deleted_names:

        modified |= remove_override_lines(
            lines,
            tu,
            deleted_names
        )

    for item in changes["deleted"]:

        logger.log()
        logger.log(
            "   ⚠️ [DELETED IN BASE]"
        )

        logger.log(
            f"   '{item['signature']}'"
        )

        logger.log(
            "      -> remove override"
        )

        stats["override_removed"] += 1

    #
    # changed
    #
    changed_names = [
        x["old"]["name"]
        for x in changes["changed"]
    ]

    if changed_names:

        modified |= remove_override_lines(
            lines,
            tu,
            changed_names
        )

    for item in changes["changed"]:

        old_sig = (
            item["old"]["signature"]
        )

        new_sig = (
            item["new"]["signature"]
        )

        if append_stub(
            lines,
            new_sig
        ):
            stats["stubs_added"] += 1

        modified = True

        logger.log()
        logger.log(
            "   ⚠️ [PARAMS CHANGED]"
        )

        logger.log(
            f"   '{old_sig}'"
        )

        logger.log(
            "      -> remove override"
        )

        logger.log(
            f"      + '{new_sig} override'"
        )

        stats["override_removed"] += 1

    #
    # added
    #
    for item in changes["added"]:

        if append_stub(
            lines,
            item["signature"]
        ):
            stats["stubs_added"] += 1

        modified = True

        logger.log()
        logger.log(
            "   ✨ [NEW IN BASE]"
        )

        logger.log(
            f"   + '{item['signature']} override'"
        )

    if modified:

        Path(file_path).write_text(
            "".join(lines),
            encoding="utf-8"
        )

        stats["files_modified"] += 1

    else:

        logger.log()
        logger.log(
            "   ✅ No changes required."
        )

    #
    # Runs independent of whether the header itself changed: a header can
    # already have "void OnError(int) override;" declared (nothing to touch
    # there) while the .cpp still has no body for it — those are two
    # different questions, checked separately.
    #
    if changes["changed"] or changes["added"]:

        cpp_file = find_cpp_for_header(
            Path(file_path)
        )

        sync_cpp_implementation(
            cpp_file,
            class_name,
            changes,
            clang_args,
            logger,
            stats
        )


def main():
    #
    # Must run before anything touches cindex.Index.create() — otherwise the
    # OS loader may fail to find libclang.dll/.so/.dylib even though
    # `pip install libclang` put it on disk. See libclang.py for why.
    #
    configure_libclang()

    cleanup_old_logs()

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--old",
        required=True
    )

    parser.add_argument(
        "--new",
        required=True
    )

    parser.add_argument(
        "--src",
        required=True
    )

    args = parser.parse_args()

    include_dir = str(
        Path(args.new).parent
    )

    clang_args = [

        "-x",
        "c++",

        "-std=c++17",

        f"-I{include_dir}"
    ]

    logger = Logger()

    interface_name = (
        Path(args.new).stem
    )

    logger.log(
        "========================================================="
    )
    logger.log(
        "Interface Sync"
    )
    logger.log(
        "========================================================="
    )
    logger.log()

    logger.log(
        f"Base Interface : {interface_name}"
    )

    logger.log(
        f"Root Directory : {args.src}"
    )

    logger.log(
        f"Include Path   : {include_dir}"
    )

    logger.log(
        f"Log File       : {logger.log_file}"
    )

    logger.log()

    old_api = extract_interface(
        args.old,
        clang_args
    )

    new_api = extract_interface(
        args.new,
        clang_args
    )

    changes = compare_interfaces(
        old_api,
        new_api
    )

    headers = list(
        Path(args.src).rglob("*.h")
    )

    logger.log(
        f"Discovered Headers : {len(headers)}"
    )

    stats = {

        "headers_found":
            len(headers),

        "derived_classes":
            0,

        "files_modified":
            0,

        "override_removed":
            0,

        "stubs_added":
            0,

        "cpp_files_modified":
            0,

        "cpp_stubs_added":
            0
    }

    for file in headers:

        process_file(
            str(file),
            interface_name,
            changes,
            logger,
            stats,
            clang_args
        )

    logger.log()
    logger.log(
        "========================================================="
    )

    logger.log(
        "Summary"
    )

    logger.log(
        "========================================================="
    )

    logger.log(
        f"Headers Found     : {stats['headers_found']}"
    )

    logger.log(
        f"Derived Classes   : {stats['derived_classes']}"
    )

    logger.log(
        f"Files Modified    : {stats['files_modified']}"
    )

    logger.log(
        f"Overrides Removed : {stats['override_removed']}"
    )

    logger.log(
        f"Stubs Added       : {stats['stubs_added']}"
    )

    logger.log(
        f".cpp Files Synced : {stats['cpp_files_modified']}"
    )

    logger.log(
        f".cpp Stubs Added  : {stats['cpp_stubs_added']}"
    )

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.close()


if __name__ == "__main__":
    main()