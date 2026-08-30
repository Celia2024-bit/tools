from pathlib import Path


def _is_under(cpp_file, directory):
    """True if cpp_file lives inside `directory` (or its subfolders)."""

    if not directory:
        return True

    try:
        cpp_resolved = Path(cpp_file).resolve()
        dir_resolved = Path(directory).resolve()
    except OSError:
        return False

    return dir_resolved in cpp_resolved.parents or dir_resolved == cpp_resolved


def _rule_matches_file(exclude_rule, cpp_file):

    directory = exclude_rule.get("directory", "")
    file_name = exclude_rule.get("file", "")

    if not _is_under(cpp_file, directory):
        return False

    if file_name and Path(cpp_file).name != file_name:
        return False

    return True


def get_exclusions_for_file(cpp_file, exclude_rules):
    """
    Given a cpp file and the list of exclude rules, return:
      - whole_file_excluded (bool): True if the entire file should be skipped
      - excluded_functions (set): function names to skip within the file
        (only meaningful when whole_file_excluded is False)
    """

    whole_file_excluded = False
    excluded_functions = set()

    for exclude_rule in exclude_rules:

        if not _rule_matches_file(exclude_rule, cpp_file):
            continue

        function_name = exclude_rule.get("function", "")

        if function_name:
            excluded_functions.add(function_name)
        else:
            whole_file_excluded = True

    return whole_file_excluded, excluded_functions
