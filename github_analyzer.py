from github import Github
from github import GithubObject
import os
import codecs
from custom_types import JobProp
import params
import auth
from tqdm import tqdm
import cPickle
import waiter
import itertools
from datetime import datetime
from base_analysis import BaseAnalysis

rule_dict = {}
job_prop = JobProp(None, None, None, None)

job_prop.github = Github(auth.access_token)
job_prop.repo = job_prop.github.get_repo(params.repo_id)


def __load_cached_data():
    print 'Loading cached data at {}'.format(params.commit_cache)
    with open(params.commit_cache, 'rb') as f:
        (commit_list, order) = cPickle.load(f)
        job_prop.commit_list = commit_list
        job_prop.commit_order = order
    return


def __cache_data(data):
    print 'Saving data to {}'.format(params.commit_cache)

    with open(params.commit_cache, 'wb') as f:
        cPickle.dump(data, f)
    return


def __preload_data(since, until, branch):
    if params.load_from_cache and os.path.exists(params.commit_cache):
        __load_cached_data()
        return

    commits = job_prop.repo.get_commits(since=since, until=until, sha=branch)
    commit_list = []
    order = {}

    reversed_commits = commits.reversed

    with tqdm(desc='Fetching data') as pbar:
        for page in itertools.count():
            curr_page = waiter.retry(lambda: reversed_commits.get_page(page), job_prop.github)

            # completely finished
            if len(curr_page) == 0:
                break

            for commit in curr_page:
                waiter.retry(lambda: commit.files, job_prop.github)
                commit_list.append(commit)
                order[commit.sha] = len(commit_list)
                pbar.update(1)

    job_prop.commit_list = commit_list
    job_prop.commit_order = order

    __cache_data((commit_list, order))


def register(plugin, plugin_name):
    if not issubclass(plugin, BaseAnalysis):
        raise TypeError('Only BaseAnalysis classes can be registered')

    rule_dict[plugin_name] = plugin


def __init(since, until, branch):
    for rule_name, rule in rule_dict.items():
        rule_dict[rule_name] = rule(job_prop)

    __preload_data(since, until, branch)


def output_path():
    return params.log_path


def __check_commits():
    for commit in tqdm(job_prop.commit_list, total=len(job_prop.commit_list), desc='Commits'):
        for key, rule in rule_dict.iteritems():
            rule.check(commit)


def __verify_state():
    commits = job_prop.repo.get_commits()
    latest_commit = waiter.retry(lambda: commits[0], job_prop.github)
    waiter.retry(lambda: latest_commit.files, job_prop.github)

    for _, rule in rule_dict.iteritems():
        violations = rule.verify(latest_commit)

        if type(violations) is str or type(violations) is unicode:
            job_name = params.repo_id.split('/')[1]
            with open(os.path.join(params.log_path, 'violations-' + job_name + '.log'), 'w') as f:
                f.write(violations)


def __print_results(out_str):
    print out_str


def __write_results(out_str, rule_name):
    job_name = params.repo_id.split('/')[1]
    filename = '{}-{}.log'.format(rule_name, job_name)
    filepath = os.path.join(params.log_path, filename)
    with codecs.open(filepath, 'w', encoding='utf-8') as f:
        f.write(out_str)

    return filepath


def __convert_bounds(bound):
    if type(bound) is not str:
        return bound

    commit = job_prop.repo.get_commit(bound)
    return datetime.strptime(commit.last_modified, '%a, %d %b %Y %X %Z')


def run(since=GithubObject.NotSet, until=GithubObject.NotSet, branch=GithubObject.NotSet):
    since = __convert_bounds(since)
    until = __convert_bounds(until)

    __init(since, until, branch)
    __check_commits()

    for rule_name, rule in rule_dict.iteritems():

        __verify_state()

        output = rule.output()
        if type(output) is str or type(output) is unicode:
            __print_results(output)
            __write_results(output, rule_name)

