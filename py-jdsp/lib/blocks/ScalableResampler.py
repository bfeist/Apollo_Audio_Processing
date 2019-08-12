import numpy as np
from numpy import dot
from scipy.signal import convolve
from jdsp.util import gcd
from numba import jit

class ScalableResampler(object):
    def __init__(self, in_rate, out_rate, quality=50):
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
        lanczos_space = np.linspace(-1, 1, taps, endpoint=False)
        self.sinc = np.sinc(space) * np.sinc(lanczos_space)
        self.window = len(self.sinc)
        self.history = np.zeros(1, dtype=np.float)
        self.history_d = np.array([taps/2], dtype=np.int)
        self.in_stride = out_rate
        self.out_stride = in_rate
        self.offset = out_rate - in_rate
        self.residual = 0.0

    def delay(self):
        '''
        Return the delay, in input samples, of the resampler, when the
        input is scaled to 1.0.
        '''
        return self.window / self.in_stride / 2
    
    def calculate_strides(self, scale):
        if len(self.history_d):
            delay = self.history_d[-1]
        else:
            delay = 0
        new_sample_deltas =  delay - self.residual + scale * self.in_stride
        rounded = np.rint(new_sample_deltas).astype(np.int)
        residual = new_sample_deltas[-1] - rounded[-1]
        return residual, rounded
        
    def output_possible(self, input_scale_vec):
        #
        # How many output samples can we create with the input scale plan?
        #
        _, calculated_strides = self.calculate_strides(input_scale_vec)
        return self.output_possible_int(calculated_strides)

    def output_possible_int(self, calculated_strides):
        total_stride = calculated_strides[-1]
        return ((total_stride - self.window) // self.out_stride) + 1
    
    def process(self, data, scale, out=None):
        #
        # Set up some working buffers.
        #
        assert(np.all(scale > 0.0))
        total_len = len(self.history) + len(data)
        deltas = np.empty(total_len, dtype=np.int)
        buf = np.empty(total_len, dtype=np.float)
        
        #
        # From the input schedule, calculate a sinc stride schedule.
        # First, incorporate the current saved window samples.
        #
        deltas[:len(self.history)] = self.history_d
        
        #
        # Now calculate the schedule for the new data.
        #
        new_residual, new_deltas = self.calculate_strides(scale)
        deltas[len(self.history):] = new_deltas
        
        #
        # To keep things very accurate, keep track of the rounding error
        # that was applied to the last input sample.
        #
        self.residual = new_residual
        
        if out is None:
            #
            # Construct the output.
            #
            out = np.empty(self.output_possible_int(new_deltas),dtype=np.float)

        #
        # Set up the working sample buffer.
        #
        buf[:len(self.history)] = self.history
        buf[len(self.history):] = data
        
        #
        # Prepare a long buffer with the previously saved samples concatenated
        # with the new input samples.
        #
        start = np.where(deltas >= len(self.sinc))[0][0]
        stop = len(deltas)
        
        consumed, out = self.process_core(
            start, stop, out, buf, self.sinc, deltas, self.out_stride
        )
        
        self.history = buf[consumed:]
        self.history_d = deltas[consumed:]
        
        return out

    @staticmethod
    @jit(nopython=True)
    def process_core(start, stop, out, buf, sinc, deltas, out_stride):
        #
        # Cache some variables
        #
        window = len(sinc)
        
        i = 0
        j = 0
        k = start
        total_delta = 0
        
        while True:
            #
            # Figure out what samples can be placed in the
            # current sinc window.
            #
            if k - j > 0:
                out[i] = dot(buf[j:k], sinc[deltas[j:k]])
            else:
                # There are no samples in the window right now.
                out[i] = 0.0

            i += 1

            #
            # March the samples and deltas along.
            #
            deltas[j:k] -= out_stride
            total_delta += out_stride
            
            #
            # Handle deltas that have dropped off.
            #
            while (j < stop) and deltas[j] < 0:
                j += 1

            #
            # We can continue as long as, after pulling,
            # the last input sample sits right on the last sample of the
            # window or beyond. We can't pull the last input sample earlier
            # than this point because the sample after the last one (which
            # hasn't arrived yet) might have to be pulled in as well, and we
            # can't predict the future!
            #
            if k == stop:
                #
                # No more samples left to pull in.
                #
                break

            new_end = total_delta + window

            if (k == stop - 1) and (deltas[k] < (new_end - 1)):
                #
                # We've got one sample left and it will be pulled in
                # too far.
                #
                break
            
            while k < stop and deltas[k] < new_end:
                #
                # It might be time to incorporate a new sample into the
                # window.
                #
                deltas[k] -= total_delta
                k += 1
        
        if k < stop:
            deltas[-1] -= total_delta
         
        #
        # Return samples consumed and output.
        #
        return j, out
