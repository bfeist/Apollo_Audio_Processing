#!/usr/bin/env python
from numpy import zeros, float, empty
from scipy.signal import convolve

class MatchedFilter(object):
    def __init__(self, samples, reverse=True):
        if reverse:
            self.coeff = samples[::-1]
        else:
            self.coeff = samples
        self.taps = len(samples)
        self.history = zeros(self.taps-1, dtype=float)

    def delay(self):
        return self.taps / 2

    def process(self, data):
        buf = empty(len(data) + self.taps - 1, dtype=float)
        buf[0:self.taps-1] = self.history
        buf[self.taps-1:] = data
        out = convolve(buf, self.coeff, mode='valid')
        self.history = buf[-(self.taps - 1):]
        return out

    def done(self):
        return self.process(zeros(self.taps/2, dtype=float))
