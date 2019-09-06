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
from numpy import linspace, empty, zeros, pi, exp, multiply, conj, angle
from numpy import empty_like, float, complex64
from scipy.signal import convolve, firwin
from ..util import gcd

def lowpass(rate, bw):
    taps = rate / bw
    if taps % 2 == 0:
        taps += 1
    return taps, firwin(taps, bw, pass_zero=True, nyq=rate).astype(float)

class ToneFollower(object):
    def __init__(self, rate, tone_hz, drift_bandwidth_hz, flutter_bandwidth_hz):
        '''
        Create a playback speed detector that follows a reference tone.
        
        rate -- Input sample rate.
        tone_hz -- Tone frequency to expect/follow, in hertz.
        drift_bandwidth_hz -- Bandwidth of bandpass filter to apply around
            tone frequency. Bandpass filter will be centered on the tone
            frequency.
        flutter_bandwidth_hz -- The maximum flutter rate to detect, in hertz.

        This procesing block is useful for detecting wow and flutter in a
        signal stream provided there is a continuous reference tone to follow
        in the stream. (Like an IRIG-B timecode signal at 1 kHz, for example).
        
        The output of the procesing block is an estimation of the instantaneous
        playback speed at every input sample, scaled to the unit value (1) when
        the playback rate appears to be normal.
        '''
        # Input sample rate.
        self.rate = rate

        #
        # Set up a post-mixing filter.
        #
        self.taps, self.coeff = lowpass(rate, drift_bandwidth_hz)
        self.history = zeros(self.taps-1, dtype=complex64)

        #
        # Set up a post-FM demodulation filter.
        #
        self.angle_taps, self.acoeff = lowpass(rate, flutter_bandwidth_hz)
        self.ahistory = zeros(self.angle_taps-1, dtype=float)

        #
        # FM demodulation requires one sample of history.
        #
        self.prev_err_sample = 0

        #
        # Calculate the reference tone oscillator speed in radians-per-sample.
        #
        self.angle = (2 * pi * tone_hz) / rate
        self.r_angle = 1.0 / self.angle # Reciprocal

        #
        # Create the basis for a stable oscillator that can run correctly
        # across billions of input samples.
        #
        common = gcd(int(rate), int(tone_hz))
        self.top_r = int(tone_hz / common)
        self.bottom_r = int(rate / common)
        self.counter = 0

    def delay(self):
        '''
        Processing block delay, in samples.
        '''
        return self.taps / 2 + self.angle_taps / 2

    def process(self, data):
        #
        # Incorporate past samples into a buffer for
        # filtering the mixing output.
        #
        buf = empty(len(data) + self.taps - 1, dtype=complex64)
        buf[0:self.taps-1] = self.history

        #
        # Create an oscillator signal to be used as a reference.
        #
        start_phase = self.counter * self.angle
        oscillator_phasor = 1j * linspace(
            start_phase,
            start_phase + self.angle*len(data),
            len(data),
            endpoint=False
        )
        oscillator = exp(oscillator_phasor)

        #
        # Mix the reference signal with the input signal.
        #
        multiply(data, oscillator, out=buf[self.taps-1:])

        #
        # Filter output with low-pass filter. This creates a complex 'phase
        # error' signal.
        #
        err = convolve(buf, self.coeff, mode='valid')

        #
        # FM demodulate the resultant phase error signal, yielding a general
        # sense of the sample-by-sample frequency by which the input signal
        # differs from the generated reference signal.
        #
        diff = empty_like(err)
        diff[0] = err[0] * conj(self.prev_err_sample)
        multiply(err[1:], conj(err[:-1]), out=diff[1:])

        #
        # Set up an FM filter buffer.
        #
        demodbuf = empty(len(data) + self.angle_taps - 1, dtype=float)
        demodbuf[0:self.angle_taps-1] = self.ahistory

        #
        # Demodulate the error signal into the FM filter buffer.
        #
        demodbuf[self.angle_taps-1:] = angle(diff)

        #
        # Filter the FM signal, yielding the estimated error between the
        # playback rate and the record rate, radians-per sample. A theta
        # value of zero represents no change in playback speed. Positive
        # values represent playback speeds that are slower than recorded
        # and negative values represent speeds faster than recorded.
        #
        dtheta = convolve(demodbuf, self.acoeff, mode='valid')

        #
        # Convert radians-per-sample error signal to a detected playback
        # speed in multiplicative units relative to the sample rate.
        #
        rate = 1.0 - dtheta * self.r_angle

        #
        # Save the last output sample for future difference calculations.
        #
        self.prev_err_sample = err[-1]

        #
        # Save mixed output for future filtering.
        # Save FM demodulated output for future filtering.
        #
        self.history = buf[-(self.taps - 1):]
        self.ahistory = demodbuf[-(self.angle_taps - 1):]

        #
        # Update the oscillator.
        #
        self.counter = (self.counter + len(data)) % self.bottom_r

        return rate

    def done(self):
        '''
        Finish processing by flushing all queued samples.
        '''
        return self.process(zeros(self.delay()))
