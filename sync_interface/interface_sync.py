#!/usr/bin/env python3

import argparse
from pathlib import Path
from clang import cindex

from logger import Logger


# ==========================================================
# AST
# ==========================================================

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


def extract_interface(header_file):

    index = cindex.Index.create()

    tu = index.parse(
        header_file,
        args=[
            "-x",
            "c++",
            "-std=c++17"
        ]
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

    for name in sorted(old_names - new_names):

        changes["deleted"].append(
            old_api[name]
        )

    for name in sorted(new_names - old_names):

        changes["added"].append(
            new_api[name]
        )

    for name in sorted(old_names & new_names):

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
                "old": old_item,
                "new": new_item
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

            if child.spelling == interface_name:
                return True

    return False


# ==========================================================
# Rewrite
# ==========================================================

def remove_override_lines(
    lines,
    tu,
    target_methods
):

    modified = False

    for node in tu.cursor.walk_preorder():

        if (
            node.kind
            !=
            cindex.CursorKind.CXX_METHOD
        ):
            continue

        if node.spelling not in target_methods:
            continue

        for token in node.get_tokens():

            if token.spelling != "override":
                continue

            line_no = (
                token.location.line
            )

            idx = line_no - 1

            old_line = lines[idx]

            new_line = (
                old_line
                .replace(" override", "")
                .replace("override ", "")
            )

            if old_line != new_line:

                lines[idx] = new_line

                modified = True

    return modified


def append_stub(
    lines,
    signature
):

    stub = (
        f"    {signature} override;\n"
    )

    #
    # 防止重复追加
    #
    for line in lines:

        if (
            signature in line
            and
            "override" in line
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
        stub
    )

    return True


# ==========================================================
# Per File
# ==========================================================

def process_file(
    file_path,
    interface_name,
    changes,
    logger,
    stats
):

    index = cindex.Index.create()

    tu = index.parse(
        file_path,
        args=[
            "-x",
            "c++",
            "-std=c++17",
            f"-I{Path(file_path).parent}"
        ]
    )

    derived = False

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

                derived = True
                break

    if not derived:
        return

    stats["files_scanned"] += 1

    logger.log()
    logger.log(
        f"⚙️ Inspecting Derived Class file: "
        f"{file_path}..."
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


# ==========================================================
# Main
# ==========================================================

def main():

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

    logger = Logger()

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "override_removed": 0,
        "stubs_added": 0
    }

    old_api = extract_interface(
        args.old
    )

    new_api = extract_interface(
        args.new
    )

    changes = compare_interfaces(
        old_api,
        new_api
    )

    interface_name = (
        Path(args.new).stem
    )

    for file in Path(
        args.src
    ).rglob("*.h"):

        if file.name in [
            Path(args.old).name,
            Path(args.new).name
        ]:
            continue

        process_file(
            str(file),
            interface_name,
            changes,
            logger,
            stats
        )

    logger.log()
    logger.log(
        "================================================="
    )

    logger.log("Summary")

    logger.log(
        "================================================="
    )

    logger.log(
        f"Files Scanned     : "
        f"{stats['files_scanned']}"
    )

    logger.log(
        f"Files Modified    : "
        f"{stats['files_modified']}"
    )

    logger.log(
        f"Overrides Removed : "
        f"{stats['override_removed']}"
    )

    logger.log(
        f"Stubs Added       : "
        f"{stats['stubs_added']}"
    )

    logger.close()


if __name__ == "__main__":
    main()