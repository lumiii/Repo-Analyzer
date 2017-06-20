import abc


class BaseAnalysis(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, job_prop):
        return

    @abc.abstractmethod
    def check(self, commit):
        return

    @abc.abstractmethod
    def verify(self, commit):
        return

    @abc.abstractmethod
    def output(self):
        return
