from github import Github
import auth
import params
import git_tools
from recordtype import recordtype

TestResult = recordtype('TestResult', 'sha success')


def __run_test(tester, commit_sha):
    sha, restore = git_tools.checkout(commit_sha)

    try:
        success = tester()
    except:
        success = False

    git_tools.restore(sha, restore)

    return success


def __test_commit(tester, commit_list, index):
    commit_record = commit_list[index]

    if commit_record.success is None:
        print 'Testing commit {} : {}'.format(index, commit_record.sha)
        commit_record.success = __run_test(tester, commit_record.sha)
        print commit_record.success

    return commit_record.success


def __binary_search(tester, commit_list):
    start = 0
    end = len(commit_list) - 1

    __test_commit(tester, commit_list, start)
    __test_commit(tester, commit_list, end)

    assert commit_list[start].success is True
    assert commit_list[end].success is False

    while start <= end:
        middle = start + ((end - start) / 2)
        success = __test_commit(tester, commit_list, middle)

        if success:
            if commit_list[middle + 1].success is False:
                return commit_list[middle + 1].sha

            start = middle + 1
        else:
            if commit_list[middle - 1].success is True:
                return commit_list[middle].sha

            end = middle - 1

    return None


def find_passing_test(tester, branch, start_commit_sha, end_commit_sha):
    github = Github(auth.access_token)
    repo = github.get_repo(params.repo_id)
    start_commit = repo.get_commit(start_commit_sha)
    end_commit = repo.get_commit(end_commit_sha)
    page_list = repo.get_commits(sha=branch, since=start_commit.commit.committer.date, until=end_commit.commit.committer.date)

    commit_list = []
    for commit in page_list.reversed:
        commit_list.append(TestResult(commit.sha, None))

    return __binary_search(tester, commit_list)

