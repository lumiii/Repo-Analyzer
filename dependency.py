from __future__ import division

import difflib
import os
import params
import waiter
import zranking
from custom_types import Violation, FilePath, DependencyRecord
from path_ops import get_extension, get_filename_from_path, decompose_path
from base_analysis import BaseAnalysis

git_path = os.path.join('D:\\SampleRepo\\', params.repo_id)


class DependencyAnalysis(BaseAnalysis):
    STATUS_MODIFIED = u'modified'
    STATUS_ADDED = u'added'
    STATUS_DELETED = u'removed'
    STATUS_RENAMED = u'renamed'

    def __init__(self, g_job_prop):
        self.job_prop = g_job_prop
        self.results = {}
        self.rankings = None
        # mapping of names to a FilePath object
        # purpose of this is for all makefile records to share the same FilePath object
        # if it's describing the same path, so any renames can be applied at the same time
        # without iterating through all of our previous results
        self.makefile_index = {}

        # results = { (folder_path(str), extension(str)) : dependencyrecord }
        # dependencyrecord = (commits, makefile_records)
        # dependencyrecord.commits = [commits]
        # dependencyrecord.makefile_records = { makefilepath(str) : [commits] }

    
    def __dump_filename(self):
        (_, job_name) = os.path.split(git_path)
        return 'dump-' + job_name + '.p'

    
    def __dump_filepath(self):
        out_path = params.log_path
        return os.path.join(out_path, self.__dump_filename())

    # HELPERS : convert from one type of data into another
    
    def __filter_filelist(self, files, status):
        if type(status) is list:
            return [f for f in files if f.status in status]

        return [f for f in files if f.status == status]

    def __get_makefilepath(self, path_str):
        if path_str in self.makefile_index:
            return self.makefile_index[path_str]

        new_path = FilePath(path_str, False)
        self.makefile_index[path_str] = new_path
        return new_path

    def __delete_makefilepath(self, path):
        filepath = self.__get_makefilepath(path)
        filepath.deleted = True

    def __change_makefilepath(self, new_path, old_path):
        filepath = self.__get_makefilepath(old_path)
        filepath.path = new_path
        self.makefile_index.pop(old_path)
        self.makefile_index[new_path] = filepath

    def __convert_to_population(self):
        populations = {}
        for folder_ext, dep_record in self.results.iteritems():
            (weighted_total, total) = self.__total_weights(dep_record)
            makefile_records = dep_record.makefile_records

            for makefile_path, commits in makefile_records.iteritems():
                rate = self.__success_rate(commits, weighted_total)
                key = (folder_ext, makefile_path)
                assert key not in populations
                populations[key] = zranking.Population(rate, total, 0)

        return populations

    def __success_rate(self, commits, weighted_total):
        weight = 0
        for commit in commits:
            weight += self.job_prop.commit_order[commit.sha]

        # percentage of the weighted total this actually satisfies
        return weight / weighted_total


    def __is_merge(self, commit):
        return len(commit.parents) > 1

    # CHECKING RELATED HELPERS

    # key is folder, extension tuple
    def __init_key(self, folder_ext):
        if folder_ext not in self.results:
            self.results[folder_ext] = DependencyRecord([], {})


    def __add_path(self, source_path, makefile_str, commit):
        folder_ext = decompose_path(source_path)
        self.__init_key(folder_ext)

        self.results[folder_ext].makefile_records.setdefault(self.__get_makefilepath(makefile_str), []).append(commit)


    def __increment_count(self, path_str, commit):
        folder_ext = decompose_path(path_str)
        self.__init_key(folder_ext)

        self.results[folder_ext].commits.append(commit)


    def __check_renames(self, commit):
        for git_file in self.__filter_filelist(commit.files, DependencyAnalysis.STATUS_RENAMED):
            self.__change_makefilepath(git_file.filename, git_file.previous_filename)


    def __check_deletes(self, commit):
        for git_file in self.__filter_filelist(commit.files, DependencyAnalysis.STATUS_DELETED):
            self.__delete_makefilepath(git_file.filename)


    # TODO: deleting a single file would not be grounds for changing the evidence
    # but deleting a folder is indicative of a change in rules
    # (if there is no folder, then there can't be a rule associated)
    def __delete_path(self, path):
        return


    def __find_new_sources(self, commit):
        path_strs = []
        for git_file in self.__filter_filelist(commit.files, [DependencyAnalysis.STATUS_ADDED, DependencyAnalysis.STATUS_DELETED, DependencyAnalysis.STATUS_RENAMED]):
            path_strs.append((git_file.filename, git_file.status))

        return path_strs


    
    def __filter_changes(self, diff, diff_encoding):
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

            if out_line.startswith(u'-') or out_line.startswith(u'+'):
                output.append(out_line)

        return output


    def __file_content_changed(self, git_file):
        return git_file.additions > 0 or git_file.changes > 0 or git_file.deletions > 0

    def __get_filecontents_from_commit(self, file_path, commit):
        waiter.wait_if_empty(self.job_prop.github, calls_needed=2)

        git_tree = waiter.retry(lambda: self.job_prop.repo.get_git_tree(commit.sha, recursive=True),
                                self.job_prop.github)

        for elem in git_tree.tree:
            if file_path == elem.path:
                git_blob = waiter.retry(lambda: self.job_prop.repo.get_git_blob(elem.sha),
                                        self.job_prop.github)
                content = git_blob.content.decode(git_blob.encoding)
                return content.split('\n')

        assert False
        return None

    def __get_diff(self, git_file, commit):
        if git_file.patch is not None:
            return self.__filter_changes(git_file.patch.split('\n'), None)

        # an empty change, usually simple rename or adding file without content - no new changes to be observed
        if not self.__file_content_changed(git_file):
            return []

        content = self.__get_filecontents_from_commit(git_file.filename, commit)

        if git_file.status == DependencyAnalysis.STATUS_ADDED:
            return self.__filter_changes(difflib.unified_diff([''], content, n=0), 'utf-8')

        assert git_file.status == DependencyAnalysis.STATUS_MODIFIED or git_file.status == DependencyAnalysis.STATUS_RENAMED
        if git_file.status == DependencyAnalysis.STATUS_MODIFIED:
            prev_filename = git_file.filename
        else: # STATUS_RENAMED
            prev_filename = git_file.previous_filename

        prev_content = self.__get_filecontents_from_commit(prev_filename, commit.parents[0])

        return self.__filter_changes(difflib.unified_diff(prev_content, content, n=0), 'utf-8')

    def __check_diff_for_source(self, git_file, commit, source_path_strs_type, matches):
        # look through all potential makefiles' diffs and record instances
        # of mentions of new source paths - this is a heuristic but
        # are likely dependency hints
        makefile_path = git_file.filename

        diff = self.__get_diff(git_file, commit)
        for line in diff:
            for path_str, change_type in source_path_strs_type:
                if (line.startswith(u'-') and change_type == DependencyAnalysis.STATUS_DELETED) or \
                        (line.startswith(u'+') and change_type in [DependencyAnalysis.STATUS_ADDED, DependencyAnalysis.STATUS_RENAMED]):
                    # already seen, already captured
                    if path_str in matches and makefile_path in matches[path_str]:
                        continue

                    filename = get_filename_from_path(path_str)
                    extension = get_extension(path_str)
                    if extension is not None and filename in line:
                        matches.setdefault(path_str, set()).add(makefile_path)

    # returns { new_source_path, [makefile1, makefile2...]}
    def __check_changed_filename(self, commit, source_path_strs_type):
        matches = {}

        # get a list of files with changes that still remain after this commit (no deletes)
        file_list = self.__filter_filelist(commit.files,
                                           [DependencyAnalysis.STATUS_ADDED, DependencyAnalysis.STATUS_RENAMED, DependencyAnalysis.STATUS_MODIFIED])

        for git_file in file_list:
            self.__check_diff_for_source(git_file, commit, source_path_strs_type, matches)

        return matches

    def __check_commit(self, commit):
        self.__check_renames(commit)
        self.__check_deletes(commit)

        new_sources_path_strs_type = self.__find_new_sources(commit)
        # if no new sources appear in this diff, then there's nothing to record
        if not new_sources_path_strs_type:
            return

        # check the relationship mapping between a new file
        # and another source dependency (i.e. makefile)
        matches = self.__check_changed_filename(commit, new_sources_path_strs_type)

        # record each match and
        # also record each new source that has no dependencies
        for source_path_str, _ in new_sources_path_strs_type:
            if source_path_str in matches:
                make_list = matches[source_path_str]
                for makefile_str in make_list:
                    self.__add_path(source_path_str, makefile_str, commit)
            else:
                # empty result
                self.__add_path(source_path_str, '', commit)

            self.__increment_count(source_path_str, commit)

    # POST CHECKING PROCESSING

    # return weight with count (weighted), and also population size(n)
    def __total_weights(self, dep_record):
        weight = 0
        for commit in dep_record.commits:
            weight += self.job_prop.commit_order[commit.sha]

        return weight, len(dep_record.commits)

    def __trim_all(self):
        for folder_ext, dep_record in self.results.iteritems():
            for makefile_path in dep_record.makefile_records.keys():
                if makefile_path.deleted:
                    dep_record.makefile_records.pop(makefile_path)

    def __zrank_all(self):
        populations = self.__convert_to_population()
        return zranking.compute_ranking(populations)

    def __begin_summary_str(self, folder_ext, dep_record):
        (filepath, extension) = folder_ext
        if extension is not None:
            out_str = "Files: {}/*.{}\n".format(filepath, extension)
        else:
            out_str = "Files: {}/*\n".format(filepath)

        makefile_path = dep_record.makefile_records.iterkeys().next()
        out_str += "Total occurrences: {}\n".format(len(dep_record.commits))
        assert (self.rankings[(folder_ext, makefile_path)].total == len(dep_record.commits))

        # out_str += "Commits:\n"
        # for commit in dep_record.commits:
        #     out_str += commit.sha + '\n'

        return out_str

    
    def __makefile_summary_str(self, folder_ext, dep_record):
        out_str = ""
        # sort result by highest z score
        sorted_count = sorted(dep_record.makefile_records.items(),
                              key=lambda elem: self.rankings[(folder_ext, elem[0])].score, reverse=True)

        # limit output to 10 values
        for makefile, commits in sorted_count[:9]:
            score = self.rankings[(folder_ext, makefile)].score
            size = len(commits)
            if makefile.path == '':
                out_str += "No dependency({}): {}\n".format(size, score)
            else:
                out_str += "{}({}): {}\n".format(makefile.path, size, score)

        return out_str

    
    def __check_makefile_for_source(self, source, makefile):
        with open(makefile) as f:
            for line in f:
                if source in unicode(line, encoding='utf-8'):
                    return True

        return False

    
    def __single_no_dep(self, dep_record):
        return len(dep_record.makefile_records) == 1 and dep_record.makefile_records.keys()[0].path == ''

    def __rules_to_str(self):
        out_str = ""
        # sort by alphabetical folder / extension order
        sorted_results = sorted(self.results.items(), key=lambda elem: (elem[0][1], elem[0][0]))

        for folder_ext, dep_record in sorted_results:
            if len(dep_record.makefile_records) > 0 \
                    and len(dep_record.commits) >= 10 and not self.__single_no_dep(dep_record):
                out_str += self.__begin_summary_str(folder_ext, dep_record)
                out_str += self.__makefile_summary_str(folder_ext, dep_record)
                out_str += '\n'

        return out_str

    def check(self, commit):
        # don't process merges since we would also have had processed the 'real' change to prevent double counting
        # TODO: potentially erroneous if a rename occurs that the merge observes but not the real change
        if self.__is_merge(commit):
            return

        self.__check_commit(commit)

    def verify(self, tree):
        self.__finalize()

        root = git_path
        violations = []

        for folder_ext, dep_record in self.results.iteritems():
            if len(dep_record.makefile_records) == 0:
                continue

            sorted_count = sorted(dep_record.makefile_records.items(),
                                  key=lambda elem: self.rankings[(folder_ext, elem[0])].score, reverse=True)
            makefile_path = sorted_count[0][0]
            # no dependency, nothing to check
            if makefile_path.path == '':
                continue

            (folder, extension) = folder_ext

            makefile_fullpath = os.path.join(root, makefile_path.path)
            path = os.path.join(root, folder)
            if extension is not None and os.path.exists(path) and os.path.exists(makefile_fullpath):
                for filename in os.listdir(path):
                    if filename.endswith('.' + extension) and not self.__check_makefile_for_source(filename, makefile_fullpath):
                            violations.append(Violation(os.path.join(folder, filename),
                                                        "Not in expected makefile: " + makefile_path.path))

        out_str = ''

        for violation in violations:
            out_str += '{} : {}\n'.format(violation.filepath, violation.rule_desc)

        return out_str

    def output(self):
        return self.__rules_to_str()

    def __finalize(self):
        self.__trim_all()
        self.rankings = self.__zrank_all()
        return
