import difflib
import os
import pickle
import params

file_add_change_types = ['A', 'D', 'R']
job_prop = {}
results = {}
# hacky, hope no collisions here
total_count = "~~counter~~"
 # (folder_path, extension) : {make_file: count, makefile2: count2...}


def dump_filename():
    (_, job_name) = os.path.split(params.git_path)
    return 'dump-' + job_name + '.p'


def dump_filepath():
    out_path = params.log_path
    return os.path.join(out_path, dump_filename())


def __get_extension(path):
    if path.find('.') == -1:
        return None

    return path.split('.')[-1]


def __decompose_path(filepath):
    (folder, filename) = os.path.split(filepath)
    extension = __get_extension(filename)
    return folder, extension


def __init_key(key):
    if key not in results:
        results[key] = {}
        results[key][total_count] = []


def __add_path(filepath, make_file, hexsha):
    key = __decompose_path(filepath)
    __init_key(key)

    results[key].setdefault(make_file, []).append(hexsha)


def __increment_count(filepath, hexsha):
    key = __decompose_path(filepath)
    __init_key(key)

    results[key][total_count].append(hexsha)


def __get_filename_from_path(filepath):
    (_, filename) = os.path.split(filepath)
    return filename


def __check_renames(diffs):
    for diff in diffs.iter_change_type('R'):
        oldpath = diff.a_path.encode(job_prop['encoding'])
        newpath = diff.b_path.encode(job_prop['encoding'])
        __rename_paths(newpath, oldpath)


def __rename_paths(newpath, oldpath):
    # go through all the results and switch up all the references
    print "changing " + oldpath + " to " + newpath
    for key, makefiles in results.iteritems():
        if oldpath in makefiles:
            if newpath not in makefiles:
                makefiles[newpath] = []

            makefiles[newpath] += makefiles.pop(oldpath)

    return


def __find_source_filepaths(diffs):
    filepaths = []
    for change_type in file_add_change_types:
        for diff in diffs.iter_change_type(change_type):
            filepath = diff.b_path.encode(job_prop['encoding'])
            filepaths.append(filepath)

    return filepaths


def __check_changed_filename(diffs, filepaths):
    matches = {}
    for diff in diffs.iter_change_type('M'):
        makefile_path = diff.b_path.encode(job_prop['encoding'])
        stream_a = diff.a_blob.data_stream
        data_a = stream_a.read()
        data_b = diff.b_blob.data_stream.read()
        for line in difflib.unified_diff(data_a.split('\n'), data_b.split('\n'), n=0):
            if line[0] == '-' or line[0] == '+':
                for filepath in filepaths:
                    if filepath in matches and makefile_path in matches[filepath]:
                        continue

                    filename = __get_filename_from_path(filepath)
                    extension = __get_extension(filepath)
                    if extension is not None and line.find(filename) > -1:
                        matches.setdefault(filepath, set()).add(makefile_path)

    return matches


def check(commit):
    diffs = commit.diff(commit.hexsha + "~1")
    __check_diffs(diffs, commit.hexsha)


def __check_diffs(diffs, hexsha):
    __check_renames(diffs)

    filepaths = __find_source_filepaths(diffs)
    if not filepaths:
        return

    matches = __check_changed_filename(diffs, filepaths)
#     filepath: [list of affected makefiles]
    for filepath, make_list in matches.iteritems():
        for make_file in make_list:
            __add_path(filepath, make_file, hexsha)

        __increment_count(filepath, hexsha)

    for filepath in filepaths:
        if filepath not in matches:
            # empty result
            __add_path(filepath, '', hexsha)
            __increment_count(filepath, hexsha)


def __rules_to_str():
    out_str = ""
    sorted_results = sorted(results.items(), key=lambda elem: (elem[0][1], elem[0][0]))
    # for key, commits in results.iteritems():
    for key, commits in sorted_results:
        (filepath, extension) = key

        if extension is not None:
            out_str += "Files: {}/*.{}\n".format(filepath, extension)
        else:
            out_str += "Files: {}/*\n".format(filepath)

        sorted_count = sorted(commits.items(), key=lambda elem: len(elem[1]), reverse=True)
        out_str += "Total occurrences: {}\n".format(len(commits[total_count]))

        for makefile, hash_arr in sorted_count:
            if makefile == '':
                out_str += "No dependency: {}\n".format(len(hash_arr))
            elif makefile != total_count:
                out_str += "{} : {}\n".format(makefile, len(hash_arr))
        out_str += "\n"

    return out_str


def init(g_job_prop):
    global job_prop
    job_prop = g_job_prop
    return


def verify(commit):
    return


def output():
    with open(dump_filepath(), 'w') as f:
        pickle.dump(results, f)

    return __rules_to_str()
