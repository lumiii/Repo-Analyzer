from github import Github
import os
import subprocess
import dependency
from custom_types import Rule, Job, JobProp
import params
import auth
from tqdm import tqdm

# curr_job = Job("D:\\Makefile\\openage", ['makefile', '.cmake', 'cmakelists'], ['.cpp'])

rule_dict = {'dependency': Rule(dependency.init, dependency.check, dependency.verify, dependency.output)}
job_prop = JobProp(None, None)
curr_job = Job(params.git_path)


def __calculate_order(commits):
    order = {}
    # commits are in reverse chronological order
    for i, commit in enumerate(tqdm(commits.reversed, desc='Calculating order')):
        order[commit.sha] = i + 1
    return order


def init():
    github = Github(auth.access_token)
    repo = github.get_repo(params.repo_id)
    job_prop.repo= repo
    job_prop.commit_order = __calculate_order(repo.get_commits())

    for _, rule in rule_dict.iteritems():
        rule.init(job_prop)


def output_path():
    return params.log_path


def __check_commits():
    # reverse for chronological order - older to newer
    commits = job_prop.repo.get_commits()

    size = len(job_prop.commit_order)

    for commit in tqdm(commits.reversed, total=size, desc='Commits'):
        for key, rule in rule_dict.iteritems():
            rule.check(commit)


def __verify_state():
    for _, rule in rule_dict.iteritems():
        violations = rule.verify(None)
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
    __check_commits()

    for _, rule in rule_dict.iteritems():
        output = rule.output()
        __print_results(output)
        outfile = __write_results(output)

        __verify_state()

        subprocess.call(["C:\\Windows\\System32\\notepad.exe", outfile])


init()
run()
