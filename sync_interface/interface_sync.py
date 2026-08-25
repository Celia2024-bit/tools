#!/usr/bin/env python3

import argparse
from pathlib import Path

from clang import cindex

from logger import Logger

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


def main():
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

    logger.log()
    logger.log(
        f"Log written to: {logger.log_file}"
    )

    logger.close()


if __name__ == "__main__":
    main()