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
import numpy as np
from numpy import dot
from scipy.signal import convolve
from math import gcd

class RationalResampler(object):
    def __init__(self, in_rate, out_rate, quality=10):
        '''
        Rational upsampler.
        
        in_rate -- Input sample rate. (integer)
        out_rate -- Output sample rate. (integer)
        quality -- The number of input samples to evaluate at any one time
            when producing an output sample. The more samples, the better.
        
        Because the resampler is rational, the units used for in_rate and
        out_rate really don't matter. The code will find the best true
        integer ratio for the combination.
        '''
        
        # Make sure number of input samples is odd.
        if (quality % 2) == 0:
            quality += 1
        
        #
        # Normalize the rates.
        #
        d = gcd(in_rate, out_rate)
        in_rate /= d
        out_rate /= d

        #
        # Calculate the number of sinc taps required to
        # hold the input samples, evenly spaced and centered
        # on the top point.
        #
        taps = out_rate * (quality - 1)
        
        #
        # Calculate the sinc unit sampling rate.
        # (1 = input rate equals output rate)
        # (.5 = input rate equals 1/2 output rate)
        #
        side = int(quality / 2)
        
        space = np.linspace(-side, side, taps, endpoint=False)
        self.sinc = np.sinc(space)
        self.window = quality-1
        self.history = np.zeros(self.window-1, dtype=np.float64)
        self.in_stride = out_rate
        self.out_stride = in_rate
        self.offset = out_rate - in_rate

    def delay(self):
        '''
        Return the delay, in input samples, of the resampler.
        '''
        return self.window / 2
        
    def output_possible(self, input_len):
        #
        # How many output samples can we create with this input?
        #
        return (((input_len-1) * self.in_stride + self.offset) // self.out_stride) + 1

    def max_output_possible(self, input_len):
        #
        # What's the maximum number of output samples a given input
        # buffer size could generate?
        #
        return (((input_len-1) * self.in_stride) // self.out_stride) + 2
        
    def process(self, data, out=None):
        if out is None:
            #
            # Construct the output.
            #
            out = np.empty(self.output_possible(len(data)), dtype=np.float64)
        
        #
        # Cache some variables
        #
        offset = self.offset
        out_stride = self.out_stride
        in_stride = self.in_stride
        sinc = self.sinc
        window = self.window

        #
        # Prepare a long buffer with the previously saved samples concatenated
        # with the new input samples.
        #
        buf = np.empty(window-1 + len(data), dtype=np.float64)
        buf[0:window-1] = self.history
        buf[window-1:] = data
        
        i = 0
        for j in range(len(data)):
#            if offset == 0:
#                #
#                # When the input and output line up exactly, the
#                # sinc coefficients line up such that only the middle
#                # sample of the window actually contributes anything.
#                #
#                out[i] = buf[j+window/2]
#                offset = in_stride - out_stride
#                i += 1
            while offset >= 0:
                out[i] = dot(buf[j:j+window], sinc[offset::in_stride])
                offset -= out_stride
                i += 1
            offset += in_stride
        
        self.sinc_offset = offset
        self.history = buf[-(window-1):]
        
        return out
