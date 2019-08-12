#!/usr/bin/env python
from numpy import linspace, empty, zeros, pi, exp, multiply, conj, angle
from numpy import empty_like
from scipy.signal import convolve, firwin
from ..util import gcd

class ToneFollower(object):
    def __init__(self, rate, tone_hz, drift_bandwidth_hz, flutter_bandwidth_hz):
        # Input sample rate.
        self.rate = rate
        
        #
        # Set up a post-mixing filter.
        #
        taps = rate / drift_bandwidth_hz
        if taps % 2 == 0:
            taps += 1
        self.taps = taps
        self.coeff = firwin(taps, drift_bandwidth_hz,  pass_zero=True, nyq=rate)
        self.history = zeros(self.taps-1, dtype='complex64')

        #
        # Set up a post-FM demodulation filter.
        #
        angle_taps = rate / flutter_bandwidth_hz
        if angle_taps % 2 == 0:
            angle_taps += 1
        self.angle_taps = angle_taps
        self.acoeff = firwin(angle_taps, flutter_bandwidth_hz, pass_zero=True, nyq=rate)
        self.ahistory = zeros(self.angle_taps-1, dtype='float')

        self.prev_err_sample = 0
        self.angle = (2 * pi * tone_hz) / rate

        #
        # Create the basis for a stable oscillator that can run correctly
        # across billions of input samples.
        #
        common = gcd(int(rate), int(tone_hz))
        self.top_r = int(tone_hz / common)
        self.bottom_r = int(rate / common)
        self.counter = 0
    
    def delay(self):
        return self.taps / 2 + self.angle_taps / 2
    
    def process(self, data):
        buf = empty(len(data) + self.taps - 1, dtype='complex64')
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
        thetabuf = empty(len(data) + self.angle_taps - 1, dtype='float')
        thetabuf[0:self.angle_taps-1] = self.ahistory
        
        #
        # Demodulate the error signal into the FM filter buffer.
        #
        thetabuf[self.angle_taps-1:] = angle(diff)
        
        #
        # Filter the FM signal.
        #
        theta = convolve(thetabuf, self.acoeff, mode='valid')

        #
        # Save the last output sample for future difference calculations.
        #
        self.prev_err_sample = err[-1]
        
        #
        # Save mixed output for future filtering.
        # Save FM demodulated output for future filtering.
        #
        self.history = buf[-(self.taps - 1):]
        self.ahistory = thetabuf[-(self.angle_taps - 1):]
        
        #
        # Update the oscillator.
        #
        self.counter = (self.counter + len(data)) % self.bottom_r

        return theta
