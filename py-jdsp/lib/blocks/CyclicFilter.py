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
import numpy

class CyclicFilter(object):
    def __init__(self, rate, cycle_freq, alpha):
        self.cycle = rate / cycle_freq
        self.alpha = alpha
        self.history = numpy.zeros(self.cycle, dtype='float64')
        self.offset = 0
    
    def delay(self):
        return 0
    
    def process(self, data, out=None):
        ld = len(data)
        if out is None:
            out = numpy.empty(ld, dtype='float64')
        
        #
        # Try to complete the current remainder of the cyclic
        # buffer first.
        #
        if self.offset != 0:
            to_next_offset = self.cycle - self.offset
            l = min(ld, to_next_offset)
            out = data[:l] - self.history[self.offset:l]
            self.history[self.offset:l] *= (1 - self.alpha)
            self.history[self.offset:l] += data[:l] * self.alpha
            self.offset = (self.offset + l) % self.cycle
            s = l
        else:
            s = 0
        
        while s + self.cycle <= ld:
            end = s + self.cycle
            out[s:end] = data[s:end] - self.history
            self.history *= (1 - self.alpha)
            self.history += data[s:end] * self.alpha
            s = end
        
        #
        # Process any remaining un-aligned data.
        #
        if s < ld:
            end = ld - s
            out[s:ld] = data[s:ld] - self.history[:end]
            self.history[:end] *= (1 - self.alpha)
            self.history[:end] += data[s:ld] * self.alpha
            self.offset = end
        
        return out

    def done(self, out=None):
        '''This block induces no delay, so there is nothing to do.'''
        if out is None:
            out = numpy.empty(0, dtype='float64')
        return out
