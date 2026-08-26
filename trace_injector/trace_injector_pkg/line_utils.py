def already_injected(
    lines,
    brace_idx
):

    begin = brace_idx + 1
    end = min(
        brace_idx + 8,
        len(lines)
    )

    for i in range(begin, end):

        if "ScopeTrace trace" in lines[i]:
            return True

    return False


def find_open_brace_line(
    lines,
    start_line,
    end_line
):

    begin = start_line - 1

    end = min(
        end_line,
        len(lines)
    )

    for i in range(begin, end):

        if "{" in lines[i]:
            return i

    return None
