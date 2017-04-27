from collections import namedtuple
from recordtype import recordtype

Job = namedtuple("Job", ["git_path"])
Rule = namedtuple("Rule", ["init", "check", "verify", "output"])
Violation = namedtuple("Violation", ["filepath", "rule_desc"])

DependencyRecord = recordtype('DependencyRecord', 'commits makefile_records')
# stores all the information that may be needed
DiffJob = namedtuple('DiffJob', ['commit', 'diffs'])
FilePath = recordtype('FilePath', 'path deleted')
