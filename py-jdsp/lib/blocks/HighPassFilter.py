#!/usr/bin/env python
import numpy
from scipy.signal import convolve, firwin

class HighPassFilter(object):
    def __init__(self, rate, taps, cutoff_freq):
        self.rate = rate
        self.taps = taps
        self.coeff = firwin(taps, cutoff_freq, pass_zero=False, fs=rate)
        self.history = numpy.zeros(self.taps-1, dtype='float')
    
    def delay(self):
        return self.taps / 2
    
    def process(self, data):
        buf = numpy.empty(len(data) + self.taps - 1, dtype='float')
        buf[0:self.taps-1] = self.history
        buf[self.taps-1:] = data
        out = convolve(buf, self.coeff, mode='valid')
        self.history = buf[-(self.taps - 1):]
        return out
