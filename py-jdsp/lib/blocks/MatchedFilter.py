#
# Copyright 2019 Jeremy Cooper.
#
# This file is unpublished proprietary source code. It is licensed
# for use by members of the the Apollo Audio project ("ApolloAudio"),
# who are determined at the sole discretion of Ben Feist, for use on archival
# audio produced by NASA's Apollo programs ("Apollo Material"), determined
# at the sole discretion of Jeremy Cooper.
#
# Any use outside of ApolloAudio, and/or on material other than Apollo
# Material is prohibited.
#
from numpy import zeros, float64, empty
from scipy.signal import convolve

class MatchedFilter(object):
    def __init__(self, samples, reverse=True):
        if reverse:
            self.coeff = samples[::-1]
        else:
            self.coeff = samples
        self.taps = len(samples)
        self.history = zeros(self.taps-1, dtype=float64)

    def delay(self):
        return self.taps / 2

    def process(self, data):
        buf = empty(len(data) + self.taps - 1, dtype=float64)
        buf[0:self.taps-1] = self.history
        buf[self.taps-1:] = data
        out = convolve(buf, self.coeff, mode='valid')
        self.history = buf[-(self.taps - 1):]
        return out

    def done(self):
        return self.process(zeros(self.taps/2, dtype=float64))
