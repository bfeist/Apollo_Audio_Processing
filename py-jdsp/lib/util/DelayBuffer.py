#!/usr/bin/env python
import numpy as np

class DelayBuffer(object):
    def __init__(self, delay=0, zero_stuff=True):
        self.sample_number = -delay
        self.buffer = np.empty(1000, dtype='float')
        self.count = 0
        self.size = 1000
        if zero_stuff and delay != 0:
            self.add(np.zeros(delay, dtype='float'))

    def add(self, samples):
        l = len(samples)
        if l + self.count > self.size:
            newsize = self.size + l
            newbuffer = np.empty(newsize, dtype='float')
            newbuffer[:self.count] = self.buffer[:self.count]
            self.buffer = newbuffer
            self.size = newsize
        self.buffer[self.count:self.count+l] = samples
        self.count += l

    def consume(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        assert(have == 1)
        newcount = self.count - end
        self.buffer[:newcount] = self.buffer[end:self.count]
        self.sample_number += end
        self.count = newcount

    def get(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        assert(have == 1)
        return self.buffer[off:end]

    def have(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        return have

    def find(self, sample_number, count):
        if sample_number < self.sample_number:
            # We'll never have it.
            return -1, None, None
        sample_number -= self.sample_number
        end = sample_number + count
        if end > self.count:
            # Don't have end yet
            return -2, None, None
        return 1, sample_number, end
