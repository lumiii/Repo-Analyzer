from git import Repo
import os
import subprocess
import dependency
from custom_types import Rule, Job
import params

# curr_job = Job("D:\\Makefile\\openage", ['makefile', '.cmake', 'cmakelists'], ['.cpp'])

rule_dict = {'dependency': Rule(dependency.init, dependency.check, dependency.verify, dependency.output)}
job_prop = {'encoding': ''}
curr_job = Job(params.git_path)


def output_path():
    return params.log_path


def __check_commits():
    repo = Repo(curr_job.git_path)
    assert not repo.bare

    # reverse for chronological order - older to newer
    if params.max_commit == 0:
        commits = list(repo.iter_commits())
    else:
        commits = list(repo.iter_commits(max_count=params.max_commit))

    commits.reverse()

    # remove the first commit, it has no state to diff against
    commits = commits[1:]

    job_prop['encoding'] = commits[0].encoding
    job_prop['repo'] = repo

    print "# of commits: {}".format(len(commits))

    for i, commit in enumerate(commits):
        print "Checking commit {}: {}".format(i, commit.hexsha)
        for key, rule in rule_dict.iteritems():
            rule.check(commit)


def __verify_state():
    repo = Repo(curr_job.git_path)
    assert not repo.bare

    for _, rule in rule_dict.iteritems():
        violations = rule.verify(repo.heads.master.commit.tree)
        (_, job_name) = os.path.split(curr_job.git_path)
        with open(os.path.join(params.log_path, 'violations-' + job_name + '.log'), 'w') as f:
            for violation in violations:
                f.write(violation.filepath + " : " + violation.rule_desc + "\n")


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
    for _, rule in rule_dict.iteritems():
        rule.init(job_prop)

    __check_commits()

    for _, rule in rule_dict.iteritems():
        output = rule.output()

    __print_results(output)
    outfile = __write_results(output)

    __verify_state()

    subprocess.call(["C:\\Windows\\System32\\notepad.exe", outfile])


run()
