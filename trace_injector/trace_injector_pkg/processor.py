from .file_discovery import find_cpp_files
from .injector import inject_trace_into_file
from .remover import remove_trace_from_file


def process_rule(
    rule,
    mode,
    logger,
    stats
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

        if mode == "remove_trace":

            remove_trace_from_file(
                cpp_file,
                logger,
                stats
            )

        else:

            inject_trace_into_file(
                cpp_file,
                function_name,
                logger,
                stats
            )
