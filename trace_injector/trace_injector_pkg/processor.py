from .excludes import get_exclusions_for_file
from .file_discovery import find_cpp_files
from .injector import inject_trace_into_file
from .payloads import BUILT_IN_PAYLOADS, payloads_for_rule
from .remover import remove_trace_from_file


def process_rule(
    rule,
    mode,
    exclude_rules,
    logger,
    stats,
    include_dirs=None,
    payload_table=None
):

    directory = rule.get(
        "directory",
        ""
    )

    file_name = rule.get(
        "file",
        ""
    )

    function_name = rule.get(
        "function",
        ""
    )

    base_class = rule.get(
        "base_class",
        ""
    )

    if payload_table is None:
        payload_table = BUILT_IN_PAYLOADS

    payload_names = payloads_for_rule(
        rule,
        mode,
        payload_table
    )

    cpp_files = find_cpp_files(
        directory,
        file_name
    )

    for cpp_file in cpp_files:

        stats["files_scanned"] += 1

        logger.log()
        logger.log(
            f"⚙️ Processing: {cpp_file}"
        )

        whole_file_excluded, excluded_functions = get_exclusions_for_file(
            cpp_file,
            exclude_rules
        )

        if whole_file_excluded:

            logger.log(
                "   🚫 Excluded (whole file)"
            )
            stats["files_excluded"] += 1
            continue

        if mode == "remove":

            remove_trace_from_file(
                cpp_file,
                logger,
                stats,
                target_function=function_name,
                target_base_class=base_class,
                excluded_functions=excluded_functions,
                include_dirs=include_dirs,
                payload_names=payload_names
            )

        else:

            inject_trace_into_file(
                cpp_file,
                function_name,
                logger,
                stats,
                excluded_functions=excluded_functions,
                target_base_class=base_class,
                include_dirs=include_dirs,
                payload_names=payload_names,
                payload_table=payload_table
            )
