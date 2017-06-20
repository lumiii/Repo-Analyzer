import github_analyzer
from datetime import datetime
from dependency import DependencyAnalysis
from owner import OwnerAnalysis

# github_analyzer.register(DependencyAnalysis, 'dependency-analysis')
github_analyzer.register(OwnerAnalysis, 'owner-analysis')
# since = datetime(year=2017, month=1, day=1, hour=0, minute=0)
# until = datetime(year=2017, month=5, day=17, hour=0, minute=0)
github_analyzer.run()
