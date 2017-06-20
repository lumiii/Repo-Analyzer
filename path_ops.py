import os


def get_extension(path_str):
    if path_str.find('.') == -1:
        return None

    return path_str.split('.')[-1]


def get_filename_from_path(path_str):
    (_, filename) = os.path.split(path_str)
    return filename


def decompose_path(path_str):
    (folder, filename) = os.path.split(path_str)
    extension = get_extension(filename)
    return folder, extension