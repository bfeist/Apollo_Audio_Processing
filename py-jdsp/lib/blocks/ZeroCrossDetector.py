#!/usr/bin/env python
import numpy
from numba import jit

class ZeroCrossDetector(object):
    def __init__(self, rate, freq):
        self.last = 1.0
        self.minimum_width = int(float(rate) / float(freq) * .8)
        self.running = self.minimum_width
        self.last_cross = 0

    def process(self, data):
        #
        # Prepare a buffer of samples, including the last sample given in the
        # previous process.
        #
        data = prepend(data, self.last, 'float')

        #
        # Find those points in the buffer which are positive.
        #
        positive = data > 0.0

        #
        # Find the crossing points -- positions where the previous sample is
        # negative and the current sample is positive.
        #
        crossed = (~positive[:-1]) & positive[1:]
        indexes = prepend(numpy.where(crossed)[0], self.last_cross, 'int32')

        #
        # Calculate the distance between each zero-crossing point.
        #
        index_diffs = indexes[1:] - indexes[:-1]

        #
        # Cache some variables that will be used in the tight loop.
        #
        running = self.running
        minimum_width = self.minimum_width

        #
        # Construct an output for the filtering engine.
        #
        out = numpy.empty(len(index_diffs), dtype='int32')

        n, running = self.process_internal(running, minimum_width, index_diffs,
            out)

        if n > 0:
            #
            # There are legitimate zero-crossings detected. Interpolate the
            # actual zero-crossing point for each.
            #
            out = out[:n]
            points = data[indexes[out]+1]
            slopes = points - data[indexes[out]]
            fractions = points / slopes
            out = indexes[out]

        self.running = running
        self.last = data[-1]

        if len(indexes):
            self.last_cross = indexes[-1] - len(data)

        if n > 0:
            return out, fractions
        else:
            return numpy.empty(0, dtype='float'), numpy.empty(0, dtype='float')

    @staticmethod
    @jit(nopython=True)
    def process_internal(running, minimum_width, index_diffs, out):
        #
        # Apply some hysteresis to found zero crossing points, ensuring that
        # any noisy points are skipped.
        #
        j = 0
        for i, diff in enumerate(index_diffs):
            running += diff
            if running > minimum_width:
                # Found good crossing point. Output it.
                out[j] = i+1
                j += 1
                running = 0

        return j, running

def prepend(array, value, dtype):
    n = numpy.empty(len(array) + 1, dtype=dtype)
    n[0] = value
    n[1:] = array
    return n
