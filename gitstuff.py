from git import Repo
import os
import subprocess
import dependency
from collections import namedtuple
import params

# curr_job = Job("D:\\Makefile\\openage", ['makefile', '.cmake', 'cmakelists'], ['.cpp'])

Job = namedtuple("Job", ["git_path"])
Rule = namedtuple("Rule", ["init", "check", "verify", "output"])
rule_dict = {'dependency': Rule(dependency.init, dependency.check, dependency.verify, dependency.output)}
job_prop = {'encoding': ''}
curr_job = Job(params.git_path)


def output_path():
    return params.log_path


def __check_commits():
    repo = Repo(curr_job.git_path)
    assert not repo.bare

    if params.max_commit == 0:
        commits = list(repo.iter_commits())
    else:
        commits = list(repo.iter_commits(max_count=params.max_commit))

    # remove the first commit, it has no state to diff against
    commits = commits[:len(commits) - 1]

    job_prop['encoding'] = commits[0].encoding

    print "# of commits: {}".format(len(commits))

    for key, rule in rule_dict.iteritems():
        rule.init(job_prop)

    for i, commit in enumerate(commits):
        print "Checking commit {}: {}".format(i, commit.hexsha)
        for key, rule in rule_dict.iteritems():
            rule.check(commit)


def __verify_commits():
    repo = Repo(curr_job.git_path)
    assert not repo.bare

    commits = list(repo.iter_commits())
    # remove the first commit, it has no state to diff against
    commits = commits[:len(commits) - 1]

    for i, commit in enumerate(commits):
        print "Verifying commit {}: {}".format(i, commit.hexsha)
        for key, rule in rule_dict.iteritems():
            rule.verify(commit)


def __print_results(out_str):
    print out_str


def __write_results(out_str):
    (_, job_name) = os.path.split(curr_job.git_path)
    filename = "output-" + job_name + ".log"
    filepath = os.path.join(params.log_path, filename)
    with open(filepath, 'w') as f:
        f.write(out_str)

    return filepath


def run():
    __check_commits()
    __verify_commits()

    for key, rule in rule_dict.iteritems():
        output = rule.output()

    __print_results(output)
    outfile = __write_results(output)
    subprocess.call(["C:\\Windows\\System32\\notepad.exe", outfile])


run()
