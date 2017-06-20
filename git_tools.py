import params
from git import Repo

no_changes_msg = u'No local changes to save'


def checkout(commit_sha):
    repo = Repo(params.git_path)
    restore = len(repo.index.diff(None)) > 0 or len (repo.index.diff('HEAD')) > 0
    head_sha = repo.head.commit.hexsha

    if restore:
        repo.git.stash()

    repo.git.checkout(commit_sha)

    return head_sha, restore


def restore(commit_sha, restore):
    repo = Repo(params.git_path)

    repo.git.checkout(commit_sha)
    if restore:
        repo.git.stash('pop')

    return



# checkout(u'58df458f5c5c8d318254f8d6b3b43b42883445d8')
# restore(u'58df458f5c5c8d318254f8d6b3b43b42883445d8', True)