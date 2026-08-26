def remove_trace_from_file(
    cpp_file,
    logger,
    stats
):

    lines = cpp_file.read_text(
        encoding="utf-8"
    ).splitlines(True)

    modified = False

    i = 0

    result = []

    while i < len(lines):

        line = lines[i]

        if "ScopeTrace trace(" in line:

            logger.log(
                "   ✨ Removed ScopeTrace"
            )

            stats["trace_removed"] += 1

            modified = True

            #
            # remove block
            #
            i += 1

            while i < len(lines):

                if ");" in lines[i]:
                    i += 1
                    break

                i += 1

            #
            # remove blank line after trace
            #
            if (
                i < len(lines)
                and
                lines[i].strip() == ""
            ):
                i += 1

            continue

        result.append(line)

        i += 1

    if modified:

        cpp_file.write_text(
            "".join(result),
            encoding="utf-8"
        )

        stats["files_modified"] += 1

    else:

        logger.log(
            "   ✅ No changes required."
        )
