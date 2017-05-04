from github import Github
import os
import subprocess
import dependency
from custom_types import Rule, Job, JobProp
import params
import auth
from tqdm import tqdm
import time
import calendar
import cPickle

# curr_job = Job("D:\\Makefile\\openage", ['makefile', '.cmake', 'cmakelists'], ['.cpp'])

rule_dict = {'dependency': Rule(dependency.init, dependency.check, dependency.verify, dependency.output)}
job_prop = JobProp(None, None, None)
curr_job = Job(params.git_path)


def __wait_until(reset_time):
    wait_time = reset_time - calendar.timegm(time.gmtime())

    while wait_time > 0:
        print 'Waiting until: {}'.format(time.asctime(time.localtime(reset_time)))
        time.sleep(wait_time)
        wait_time = reset_time - calendar.timegm(time.gmtime())


def __remaining_requests(git_obj):
    return float(git_obj.raw_headers['x-ratelimit-remaining'])


def __wait_if_empty(git_obj):
    remaining = __remaining_requests(git_obj)
    if remaining <= 1:
        wait_time = float(git_obj.raw_headers['x-ratelimit-reset'])
        __wait_until(wait_time)


def __load_cached_data():
    print 'Loading cached data at {}'.format(params.commit_cache)
    with open(params.commit_cache) as f:
        (commit_list, order) = cPickle.load(f)
        job_prop.commit_list = commit_list
        job_prop.commit_order = order
    return


def __cache_data(data):
    print 'Saving data to {}'.format(params.commit_cache)

    with open(params.commit_cache, 'wb') as f:
        cPickle.dump(data, f)
    return


def __preload_data():
    if params.load_from_cache and os.path.exists(params.commit_cache):
        __load_cached_data()
        return

    commits = job_prop.repo.get_commits()
    commit_list = []
    order = {}
    # commits are in reverse chronological order
    for i, commit in enumerate(tqdm(commits.reversed, desc='Loading data')):
        __wait_if_empty(commit)

        commit_list.append(commit)
        # try just using the commit as key
        order[commit.sha] = i + 1
        #
        # if i >= 20:
        #     break

    job_prop.commit_list = commit_list
    job_prop.commit_order = order

    __cache_data((commit_list, order))

def init():
    github = Github(auth.access_token)
    job_prop.repo = github.get_repo(params.repo_id)

    __preload_data()

    for _, rule in rule_dict.iteritems():
        rule.init(job_prop)


def output_path():
    return params.log_path


def __check_commits():
    for commit in tqdm(job_prop.commit_list, total=len(job_prop.commit_list), desc='Commits'):
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
