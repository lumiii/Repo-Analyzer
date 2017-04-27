from __future__ import division
import difflib
import os
import params
import zranking
from custom_types import Violation, FilePath, DependencyRecord, DiffJob

job_prop = {}
results = {}
rankings = None
# mapping of names to a FilePath object
# purpose of this is for all makefile records to share the same FilePath object
# if it's describing the same path, so any renames can be applied at the same time
# without iterating through all of our previous results
makefile_index = {}

# results = { (folder_path(str), extension(str)) : dependencyrecord }
# dependencyrecord = (commits, makefile_records)
# dependencyrecord.commits = [commits]
# dependencyrecord.makefile_records = { makefilepath(str) : [commits] }


def dump_filename():
    (_, job_name) = os.path.split(params.git_path)
    return 'dump-' + job_name + '.p'


def dump_filepath():
    out_path = params.log_path
    return os.path.join(out_path, dump_filename())


# HELPERS : convert from one type of data into another
def __get_extension(path_str):
    if path_str.find('.') == -1:
        return None

    return path_str.split('.')[-1]


def __get_filename_from_path(path_str):
    (_, filename) = os.path.split(path_str)
    return filename


def __decompose_path(path_str):
    (folder, filename) = os.path.split(path_str)
    extension = __get_extension(filename)
    return folder, extension


def __get_makefilepath(path_str):
    if path_str in makefile_index:
        return makefile_index[path_str]

    new_path = FilePath(path_str, False)
    makefile_index[path_str] = new_path
    return new_path


def __delete_makefilepath(path):
    filepath = __get_makefilepath(path)
    filepath.deleted = True

def __change_makefilepath(new_path, old_path):
    filepath = __get_makefilepath(old_path)
    filepath.path = new_path
    makefile_index.pop(old_path)
    makefile_index[new_path] = filepath


def __convert_to_population():
    populations = {}
    for folder_ext, dep_record in results.iteritems():
        (weighted_total, total) = __total_weights(dep_record)
        makefile_records = dep_record.makefile_records

        for makefile_path, commits in makefile_records.iteritems():
            rate = __success_rate(commits, weighted_total)
            key = (folder_ext, makefile_path)
            assert key not in populations
            populations[key] = zranking.Population(rate, total, 0)

    return populations


def __success_rate(commits, weighted_total):
    weight = 0
    for commit in commits:
        weight += commit.count()

    # percentage of the weighted total this actually satisfies
    return weight / weighted_total


def __is_merge(commit):
    return len(commit.parents) > 1

# CHECKING RELATED HELPERS

# key is folder, extension tuple
def __init_key(folder_ext):
    if folder_ext not in results:
        results[folder_ext] = DependencyRecord([], {})


def __add_path(source_path, make_file, job):
    folder_ext = __decompose_path(source_path)
    __init_key(folder_ext)

    results[folder_ext].makefile_records.setdefault(__get_makefilepath(make_file), []).append(job.commit)


def __increment_count(path_str, job):
    folder_ext = __decompose_path(path_str)
    __init_key(folder_ext)

    results[folder_ext].commits.append(job.commit)


def __check_renames(diffs):
    for diff in diffs.iter_change_type('R'):
        oldpath = diff.a_path.encode(job_prop['encoding'])
        newpath = diff.b_path.encode(job_prop['encoding'])
        print "changing " + oldpath + " to " + newpath
        __change_makefilepath(newpath, oldpath)


def __check_deletes(job):
    diffs = job.diffs
    for diff in diffs.iter_change_type('D'):
        path = diff.a_path.encode(job_prop['encoding'])
        __delete_makefilepath(path)


# deleting a single file would not be grounds for changing the evidence
# but deleting a folder is indicative of a change in rules
# (if there is no folder, then there can't be a rule associated)
def __delete_path(path):
    return


def __find_new_sources(diffs):
    path_strs = []
    for change_type in ['A', 'D', 'R']:
        for diff in diffs.iter_change_type(change_type):
            path_str = diff.b_path.encode(job_prop['encoding'])
            path_strs.append((path_str, change_type))

    return path_strs


def __check_diff_for_source(diff, source_path_strs_type, matches):
    makefile_path = diff.b_path.encode(job_prop['encoding'])
    if diff.change_type.startswith('A'):
        data_b = diff.b_blob.data_stream.read()
        content_a = []
        content_b = data_b.split('\n')
    elif diff.change_type.startswith('R') or diff.change_type.startswith('M'):
        data_a = diff.a_blob.data_stream.read()
        data_b = diff.b_blob.data_stream.read()
        content_a = data_a.split('\n')
        content_b = data_b.split('\n')

    # look through all potential makefiles' diffs and record instances
    # of mentions of new source paths - this is a heuristic but
    # are likely dependency hints
    for line in difflib.unified_diff(content_a, content_b, n=0):
        for path_str, change_type in source_path_strs_type:
            if (line[0] == '-' and change_type == 'D') or (line[0] == '+' and change_type in ['A', 'R']):
                # already seen, already captured
                if path_str in matches and makefile_path in matches[path_str]:
                    continue

                filename = __get_filename_from_path(path_str)
                extension = __get_extension(path_str)
                if extension is not None and line.find(filename) > -1:
                    matches.setdefault(path_str, set()).add(makefile_path)


# returns { new_source_path, [makefile1, makefile2...]}
def __check_changed_filename(diffs, source_path_strs_type):
    matches = {}
    for change_type in ['A', 'R', 'M']:
        for diff in diffs.iter_change_type(change_type):
            __check_diff_for_source(diff, source_path_strs_type, matches)

    return matches


def __check_diffs(job):
    __check_renames(job.diffs)
    __check_deletes(job)

    new_sources_path_strs_type = __find_new_sources(job.diffs)
    # if no new sources appear in this diff, then there's nothing to record
    if not new_sources_path_strs_type:
        return

    # check the relationship mapping between a new file
    # and another source dependency (i.e. makefile)
    matches = __check_changed_filename(job.diffs, new_sources_path_strs_type)

    # record each match and
    # also record each new source that has no dependencies
    for source_path_str, _ in new_sources_path_strs_type:
        if source_path_str in matches:
            make_list = matches[source_path_str]
            for makefile_str in make_list:
                __add_path(source_path_str, makefile_str, job)
        else:
            # empty result
            __add_path(source_path_str, '', job)

        __increment_count(source_path_str, job)


# POST CHECKING PROCESSING

# return weight with count (weighted), and also population size(n)
def __total_weights(dep_record):
    weight = 0
    # TODO: consider a different heuristic than count()
    # count() doesn't necessarily represent linear ordering of commits
    for commit in dep_record.commits:
        weight += commit.count()

    return weight, len(dep_record.commits)


def __trim_all():
    for folder_ext, dep_record in results.iteritems():
        for makefile_path in dep_record.makefile_records.keys():
            if makefile_path.deleted:
                dep_record.makefile_records.pop(makefile_path)


def __zrank_all():
    populations = __convert_to_population()
    return zranking.compute_ranking(populations)


def __begin_summary_str(folder_ext, dep_record):
    (filepath, extension) = folder_ext;
    if extension is not None:
        out_str = "Files: {}/*.{}\n".format(filepath, extension)
    else:
        out_str = "Files: {}/*\n".format(filepath)

    makefile_path = dep_record.makefile_records.iterkeys().next()
    out_str += "Total occurrences: {}\n".format(len(dep_record.commits))
    assert (rankings[(folder_ext, makefile_path)].total == len(dep_record.commits))

    out_str += "Commits:\n"
    for commit in dep_record.commits:
        out_str += commit.hexsha + '\n'

    return out_str


def __makefile_summary_str(folder_ext, dep_record):
    out_str = ""
    # sort result by highest z score
    sorted_count = sorted(dep_record.makefile_records.items(),
                          key=lambda elem: rankings[(folder_ext, elem[0])].score, reverse=True)

    for makefile, commits in sorted_count:
        score = rankings[(folder_ext, makefile)].score
        size = len(commits)
        if makefile.path == '':
            out_str += "No dependency({}): {}\n".format(size, score)
        else:
            out_str += "{}({}): {}\n".format(makefile.path, size, score)

    return out_str


def __rules_to_str():
    out_str = ""
    # sort by alphabetical folder / extension order
    sorted_results = sorted(results.items(), key=lambda elem: (elem[0][1], elem[0][0]))

    for folder_ext, dep_record in sorted_results:
        if len(dep_record.makefile_records) > 0:
            out_str += __begin_summary_str(folder_ext, dep_record)
            out_str += __makefile_summary_str(folder_ext, dep_record)
            out_str += '\n'

    return out_str


# publically exposed :
# init (starts the process)
# check each commit
# verify a commit against rules
# output
def init(g_job_prop):
    global job_prop
    job_prop = g_job_prop


def check(commit):
    # don't process merges since we would also have had processed the 'real' change to prevent double counting
    # TODO: potentially erroneous if a rename occurs that the merge observes but not the real change
    if __is_merge(commit):
        return

    old_commit = job_prop['repo'].commit(commit.hexsha + "~1")
    diffs = old_commit.diff(commit)
    __check_diffs(DiffJob(commit, diffs))


def __check_makefile_for_source(source, makefile):
    with open(makefile) as f:
        for line in f:
            if source in line:
                return True

    return False


def verify(tree):
    root = params.git_path
    violations = []

    for folder_ext, dep_record in results.iteritems():
        if len(dep_record.makefile_records) == 0:
            continue

        sorted_count = sorted(dep_record.makefile_records.items(),
                              key=lambda elem: rankings[(folder_ext, elem[0])].score, reverse=True)
        makefile_path = sorted_count[0][0]
        # no dependency, nothing to check
        if makefile_path.path == '':
            continue

        (folder, extension) = folder_ext

        makefile_fullpath = os.path.join(root, makefile_path.path)
        path = os.path.join(root, folder)
        if os.path.exists(path):
            for filename in os.listdir(path):
                if filename.endswith('.' + extension) and not __check_makefile_for_source(filename, makefile_fullpath):
                        violations.append(Violation(os.path.join(folder, filename),
                                                    "Not in expected makefile: " + makefile_path.path))

    return violations


def output():
    global rankings
    __trim_all()
    rankings = __zrank_all()

    return __rules_to_str()
