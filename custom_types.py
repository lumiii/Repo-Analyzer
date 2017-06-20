from collections import namedtuple
from recordtype import recordtype

Rule = namedtuple("Rule", ["init", "check", "verify", "output"])
Violation = namedtuple("Violation", ["filepath", "rule_desc"])

DependencyRecord = recordtype('DependencyRecord', 'commits makefile_records')
# stores all the information that may be needed
DiffJob = namedtuple('DiffJob', ['commit', 'diffs'])
FilePath = recordtype('FilePath', 'path deleted')
JobProp = recordtype('JobProp', 'repo github commit_order commit_list')

