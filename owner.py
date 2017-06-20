import path_ops
from base_analysis import BaseAnalysis


class OwnerAnalysis(BaseAnalysis):
    FOLDER_OUTPUT_LIMIT = 5

    def __init__(self, job_prop):
        self.job_prop = job_prop
        self.results = {}
        # dict: folder->{owner -> set(commits}

    def __increment_owner(self, owner, folder, commit):
        if folder not in self.results:
            self.results[folder] = {}

        if owner not in self.results[folder]:
            self.results[folder][owner] = set()

        self.results[folder][owner].add(commit)

    def check(self, commit):
        folders = set()
        for git_file in commit.files:
            folder, _ = path_ops.decompose_path(git_file.filename)
            folders.add(folder)

        for folder in folders:
            self.__increment_owner(commit.commit.author.name, folder, commit)

        return

    def verify(self, commit):
        return

    def __weighted_score(self, commit_set):
        score = 0
        for commit in commit_set:
            score += self.job_prop.commit_order[commit.sha]

        return score

    def output(self):
        out_str = u''
        for folder, owner_records in sorted(self.results.items()):
            sorted_count = sorted(owner_records.items(),
                                  key=lambda elem: self.__weighted_score(elem[1]), reverse=True)

            out_str += u'Folder: {}\r\n'.format(folder)
            for i, (owner, commits) in enumerate(sorted_count):
                out_str += u'Author({}): {}\r\n'.format(len(commits), owner)

                if i >= OwnerAnalysis.FOLDER_OUTPUT_LIMIT:
                    break

            out_str += u'\r\n'

        return out_str
