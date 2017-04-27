from __future__ import division
from recordtype import recordtype
import math

Population = recordtype('Population', 'rate total score')

# populations = {key : Population, key2 : Population...etc}
def compute_ranking(populations):
    p0 = __compute_p0(populations)

    for key, population in populations.iteritems():
        denom = math.sqrt(p0 * (1 - p0) / population.total)
        population.score = (population.rate - p0)/denom

    return populations


def __compute_p0(populations):
    max_total = 0

    for key, population in populations.iteritems():
        if population.total > max_total:
            max_total = population.total

    if max_total >= 51:
        return 0.85

    p0 = 0
    for key, population in populations.iteritems():
        p0 += population.rate

    p0 /= len(populations)

    return p0
