import numpy as np
from numpy import dot
from scipy.signal import convolve
from jdsp.util import gcd
from numba import jit

class ScalableResampler(object):
    def __init__(self, in_rate, out_rate, speed_quantum=320, quality=50):
        '''
        Rational upsampler.
        
        in_rate -- Input sample rate. (integer)
        out_rate -- Output sample rate. (integer)

        speed_quantum -- The minimum instantaneous expressable speed
            difference to support, "n" in the expression "1 / n". When
            expressing a sample's playback time in the "scale" vector of
            the process method, the sample will actually be moved to the
            nearest point "k / n", where k is an integer.

            For example, a speed quantum of 100 allows for 1% changes in speed
            to be effected with no rounding. Changes below 1% will not
            instantaneously be expressed, but the residual error will be
            retained such that the change will be remembered and eventually
            make an effect on the output.

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
        # Bring up the rates if they don't support the speed quantum
        # desired.
        #
        if out_rate < speed_quantum:
            #
            # Find the lowest integer multiple to use that doesn't force
            # the output rate to go over the desired quantum.
            #
            if (speed_quantum % out_rate) == 0:
                #
                # The desired quantum is perfectly achievable. Just
                # find the simple integer multiple required to do it.
                #
                multiple = speed_quantum // out_rate
            else:
                #
                # Not a match. The new rate will exceed the quantum, but it
                # is the smallest rate which will do so, so it isn't
                # excessive.
                #
                multiple = (speed_quantum // out_rate) + 1

            #
            # Adjust the output rates so that the desired quantum is
            # achievable.
            #
            out_rate *= multiple
            in_rate *= multiple

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
        self.history_d = np.array([taps - out_rate], dtype=np.int)
        self.in_stride = out_rate
        self.out_stride = in_rate
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
        new_sample_deltas =  delay + self.residual + scale * self.in_stride
        rounded = np.rint(new_sample_deltas).astype(np.int)
        residual = new_sample_deltas[-1] - rounded[-1]
        return residual, rounded

    def output_possible(self, input_scale_vec):
        '''
        Return number of samples that can be produced for timing vector.

        If input_scale_vec is None, will return number of samples that can
        be produced when calling "done()".
        '''
        if input_scale_vec is None:
            _, samples = self.output_possible__internal_done()
            return samples

        #
        # How many output samples can we create with the input scale plan?
        # First, the timing vector must be converted to strides relative to
        # the current sinc window position.
        #
        _, calculated_strides = self.calculate_strides(input_scale_vec)

        #
        # Now compute the output possible using the stride schedule.
        #
        return self.output_possible__internal(calculated_strides)

    def output_possible__internal(self, calculated_strides):
        '''
        Return number of samples that can be produced for stride schedule.
        '''
        #
        # Get the offset at which the last sample in the schedule rests
        # with respect to the start of the sinc window.
        #
        total_stride = calculated_strides[-1]

        #
        # Output samples can be produced from the schedule as long as the
        # last sample in the schedule ends up in the last position of the
        # sinc window, but no further in.
        #
        return ((total_stride - self.window + 1) // self.out_stride) + 1

    def output_possible__internal_done(self):
        #
        # Where's the current ending sample in the sinc window scheme?
        #
        last_stride = self.history_d[-1]

        #
        # How many times can this last sample be pulled until it disappears
        # from the window?
        #
        pulls_ok = last_stride // self.out_stride

        return last_stride, pulls_ok

    def done(self, out=None):
        '''
        No more input samples are coming. Generate output from that assumption.
        '''
        #
        # Where's the current ending sample in the sinc window scheme and how
        # many times can that sample be pulled until it disappears from the
        # window?
        #
        last_stride, pulls_ok = self.output_possible__internal_done()

        #
        # Place a fake zero sample so that it will be at the very end of the
        # sinc window in the last output loop.
        #
        fake_delta = ((self.window - last_stride) - 1) \
                     + pulls_ok * self.out_stride

        oldlen = len(self.history)
        newlen = oldlen + 1

        data = np.empty(newlen, dtype=np.float)
        data[:oldlen] = self.history
        data[oldlen:] = 0.0

        deltas = np.empty(newlen, dtype=np.int)
        deltas[:oldlen] = self.history_d
        deltas[oldlen:] = int(fake_delta)

        _, out = self.process__internal(data, deltas, out)

        return out

    def process(self, data, scale, out=None):
        #
        # Every sample must have some duration.
        #
        assert(np.all(scale > 0.0))

        #
        # Set up some working buffers.
        #
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
        # Set up the working sample buffer, incorporating the history buffer
        # and the new samples.
        #
        buf[:len(self.history)] = self.history
        buf[len(self.history):] = data

        #
        # To keep things very accurate, keep track of the rounding error
        # that was applied to the last input sample.
        #
        self.residual = new_residual

        consumed, out = self.process__internal(buf, deltas, out)

        self.history = buf[consumed:]
        self.history_d = deltas[consumed:]

        return out

    def process__internal(self, data, deltas, out):
        '''
        Internal interface. Works with data on a strided schedule.
        '''
        #
        # Now calculate how many output samples we can produce from the
        # current input buffer.
        #
        output_samples = self.output_possible__internal(deltas)

        if out is None:
            #
            # Construct the output.
            #
            out = np.empty(max(output_samples,0),dtype=np.float)

        if output_samples <= 0:
            #
            # We can't produce any output right now. Just save things for
            # later.
            #
            return 0, out

        #
        # Find the first sample outside of the window in the very first
        # pass.
        #
        start = np.where(deltas >= self.window)[0]
        if len(start) == 0:
            #
            # We're in a very rare scenario where the last servicable sample
            # is exactly at the end of the current window.
            # We must be flushing the very last output.
            #
            start = len(deltas)
        else:
            start = start[0]

        #
        # Will there be any unservicable samples left over at the end of
        # the run?
        #
        total_final_delta = output_samples * self.out_stride
        last_window_end = self.window + total_final_delta
        beyonds = np.where(deltas > last_window_end)[0]

        if len(beyonds) == 0:
            #
            # No. Every sample in the schedule is servicable. (rare)
            #
            stop = len(deltas)
        else:
            #
            # Yes. Stop at the first unservicable sample.
            #
            stop = beyonds[0]

        #
        # Everything is ready. Call the inner core.
        #
        consumed = self.process_core(
            start, stop, out, data, self.sinc, deltas, self.out_stride
        )

        return consumed, out

    @staticmethod
    @jit(nopython=True)
    def process_core(start, stop, out, samples, sinc, deltas, out_stride):
        #
        # This code has many PRECONDITIONS which must be ensured before
        # it will run properly.
        #
        # assert(len(samples) == len(deltas))
        # assert(start <= len(deltas))
        # assert(stop <= len(deltas))
        # assert(start <= stop)
        # assert(np.all(deltas[:start] < len(sinc))
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
                out[i] = dot(samples[j:k], sinc[deltas[j:k]])
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
            while deltas[j] < 0:
                j += 1

            new_end = total_delta + window

            while k < stop and deltas[k] < new_end:
                #
                # It is time to incorporate a new sample into the
                # window.
                #
                deltas[k] -= total_delta
                k += 1

            #
            # We can continue as long as, after pulling, the last input
            # sample sits right on the last sample of the window or beyond.
            #
            # We can't pull the last input sample any futher into the sinc
            # window than this point because the sample after it (which hasn't
            # arrived yet) might have to be pulled in as well, if that
            # sample turns out to need to be inside this window, we'd have
            # to go back into the past to modify the output. And that's
            # not possible!
            #
            if k == stop and deltas[k-1] < window - 1:
                #
                # No more samples left to pull in.
                # Update positions of samples that weren't processed.
                #
                deltas[k:] -= total_delta
                break

        #
        # Return samples consumed.
        #
        return j
