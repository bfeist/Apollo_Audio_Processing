#!/usr/bin/env python
import numpy

class ZeroCrossDetector(object):
    def __init__(self, rate, freq):
        self.last_was_positive = False
        self.minimum_width = int(float(rate) / float(freq) * .8)
        self.running = self.minimum_width
        self.last_cross = 0
        
    def process(self, data):
        positive = prepend(data > 0.0, self.last_was_positive, 'bool')
        crossed = (~positive[:-1]) & positive[1:]
        indexes = prepend(numpy.where(crossed)[0], self.last_cross, 'int32')
        index_diffs = indexes[1:] - indexes[:-1]
        good = []
        running = self.running
        for i, diff in enumerate(index_diffs):
            running += diff
            if running > self.minimum_width:
                good.append(indexes[i+1])
                running = 0
        self.running = running
        self.last_was_positive = positive[-1]
        if len(indexes):
            self.last_cross = indexes[-1] - len(data)
        return numpy.array(good, dtype='int32')

def prepend(array, value, dtype):
    n = numpy.empty(len(array) + 1, dtype=dtype)
    n[0] = value
    n[1:] = array
    return n
