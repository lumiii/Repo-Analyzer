from __future__ import division
import difflib
import requests
import os
import params
import zranking
from custom_types import Violation, FilePath, DependencyRecord, DiffJob
from tqdm import tqdm

STATUS_MODIFIED = u'modified'
STATUS_ADDED = u'added'
STATUS_DELETED = u'removed'
STATUS_RENAMED = u'renamed'

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
def __filter_filelist(files, status):
    if type(status) is list:
        return [f for f in files if f.status in status]

    return [f for f in files if f.status == status]


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
        weight += job_prop.commit_order[commit.sha]

    # percentage of the weighted total this actually satisfies
    return weight / weighted_total


def __is_merge(commit):
    return len(commit.parents) > 1

# CHECKING RELATED HELPERS

# key is folder, extension tuple
def __init_key(folder_ext):
    if folder_ext not in results:
        results[folder_ext] = DependencyRecord([], {})


def __add_path(source_path, makefile_str, commit):
    folder_ext = __decompose_path(source_path)
    __init_key(folder_ext)

    results[folder_ext].makefile_records.setdefault(__get_makefilepath(makefile_str), []).append(commit)


def __increment_count(path_str, commit):
    folder_ext = __decompose_path(path_str)
    __init_key(folder_ext)

    results[folder_ext].commits.append(commit)


def __check_renames(commit):
    for git_file in __filter_filelist(commit.files, STATUS_RENAMED):
        __change_makefilepath(git_file.filename, git_file.previous_filename)


def __check_deletes(commit):
    for git_file in __filter_filelist(commit.files, STATUS_DELETED):
        __delete_makefilepath(git_file.filename)


# deleting a single file would not be grounds for changing the evidence
# but deleting a folder is indicative of a change in rules
# (if there is no folder, then there can't be a rule associated)
def __delete_path(path):
    return


def __find_new_sources(commit):
    path_strs = []
    for git_file in __filter_filelist(commit.files, [STATUS_ADDED, STATUS_DELETED, STATUS_RENAMED]):
        path_strs.append((git_file.filename, git_file.status))

    return path_strs


def __filter_changes(diff, diff_encoding):
    output = []

    for line in diff:
        out_line = line
        try:
            if type(out_line) is not unicode:
                if diff_encoding is not None:
                    out_line = unicode(out_line, encoding=diff_encoding)
                else:
                    out_line = unicode(out_line)
        except UnicodeWarning:
            pass
        except UnicodeDecodeError:
            pass

        if out_line.startswith(u'-') or line.startswith(u'+'):
            output.append(out_line)

    return output

def __file_content_changed(git_file):
    return git_file.additions > 0 or git_file.changes > 0 or git_file.deletions > 0


def __get_file_from_tree(file_path, commit):
    git_tree = job_prop.repo.get_git_tree(commit.sha, recursive=True)
    for git_tree_elem in git_tree.tree:
        if git_tree_elem.path == file_path:
            response = requests.get(git_tree_elem.url)
            assert response.ok

            response_json = response.json()
            content = response_json['content'].decode(response_json['encoding'])
            return content

    return None


def __get_diff(git_file, commit):
    if git_file.patch is not None:
        return __filter_changes(git_file.patch.split('\n'), None)

    # an empty change, usually simple rename or adding file without content - no new changes to be observed
    if not __file_content_changed(git_file):
        return []

    response = requests.get(git_file.raw_url)
    assert response.ok

    encoding = response.encoding
    content = response.text.split('\n')
    if git_file.status == STATUS_ADDED:
        return __filter_changes(difflib.unified_diff([''], content, n=0), encoding)

    assert git_file.status == STATUS_MODIFIED or git_file.status == STATUS_RENAMED
    if git_file.status == STATUS_MODIFIED:
        prev_filename = git_file.filename
    else: # STATUS_RENAMED
        prev_filename = git_file.previous_filename

    prev_content = __get_file_from_tree(prev_filename, commit.parents[0])
    assert prev_content is not None
    prev_content = prev_content.split('\n')

    return __filter_changes(difflib.unified_diff(prev_content, content, n=0), encoding)


def __check_diff_for_source(git_file, commit, source_path_strs_type, matches):
    # look through all potential makefiles' diffs and record instances
    # of mentions of new source paths - this is a heuristic but
    # are likely dependency hints
    makefile_path = git_file.filename

    diff = __get_diff(git_file, commit)
    for line in diff:
        for path_str, change_type in source_path_strs_type:
            if (line.startswith(u'-') and change_type == STATUS_DELETED) or \
                    (line.startswith(u'+') and change_type in [STATUS_ADDED, STATUS_RENAMED]):
                # already seen, already captured
                if path_str in matches and makefile_path in matches[path_str]:
                    continue

                filename = __get_filename_from_path(path_str)
                extension = __get_extension(path_str)
                if extension is not None and filename in line:
                    matches.setdefault(path_str, set()).add(makefile_path)


# returns { new_source_path, [makefile1, makefile2...]}
def __check_changed_filename(commit, source_path_strs_type):
    matches = {}

    # get a list of files with changes that still remain after this commit (no deletes)
    file_list = __filter_filelist(commit.files, [STATUS_ADDED, STATUS_RENAMED, STATUS_MODIFIED])

    for git_file in file_list:
        __check_diff_for_source(git_file, commit, source_path_strs_type, matches)

    return matches


def __check_commit(commit):
    __check_renames(commit)
    __check_deletes(commit)

    new_sources_path_strs_type = __find_new_sources(commit)
    # if no new sources appear in this diff, then there's nothing to record
    if not new_sources_path_strs_type:
        return

    # check the relationship mapping between a new file
    # and another source dependency (i.e. makefile)
    matches = __check_changed_filename(commit, new_sources_path_strs_type)

    # record each match and
    # also record each new source that has no dependencies
    for source_path_str, _ in new_sources_path_strs_type:
        if source_path_str in matches:
            make_list = matches[source_path_str]
            for makefile_str in make_list:
                __add_path(source_path_str, makefile_str, commit)
        else:
            # empty result
            __add_path(source_path_str, '', commit)

        __increment_count(source_path_str, commit)


# POST CHECKING PROCESSING

# return weight with count (weighted), and also population size(n)
def __total_weights(dep_record):
    weight = 0
    for commit in dep_record.commits:
        weight += job_prop.commit_order[commit.sha]

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
    (filepath, extension) = folder_ext
    if extension is not None:
        out_str = "Files: {}/*.{}\n".format(filepath, extension)
    else:
        out_str = "Files: {}/*\n".format(filepath)

    makefile_path = dep_record.makefile_records.iterkeys().next()
    out_str += "Total occurrences: {}\n".format(len(dep_record.commits))
    assert (rankings[(folder_ext, makefile_path)].total == len(dep_record.commits))

    out_str += "Commits:\n"
    for commit in dep_record.commits:
        out_str += commit.sha + '\n'

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

    __check_commit(commit)


def __check_makefile_for_source(source, makefile):
    with open(makefile) as f:
        for line in f:
            if source in unicode(line, encoding='utf-8'):
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
