from pathlib import Path


def find_cpp_files(directory, file_name):

    root = Path(directory)

    if not file_name:
        return list(
            root.rglob("*.cpp")
        )

    result = []

    for cpp in root.rglob("*.cpp"):

        if cpp.name == file_name:
            result.append(cpp)

    return result


def match_function(
    current_name,
    requested_name
):

    if not requested_name:
        return True

    return current_name == requested_name
