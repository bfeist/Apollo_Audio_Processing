import pytest
import numpy as np
from jdsp.blocks.ScalableResampler import ScalableResampler
import jdsp.io.WaveSink
import sys


@pytest.mark.skip()
def test_something():
    '''
    This appears to have been a one-off test utility. I am preserving it
    now as a possible test to re-enable some day.
    '''
    i = jdsp.io.WaveSource(sys.argv[1])
    w = jdsp.io.WaveSink(sys.argv[2], 96000, 1, 2)
    sr = ScalableResampler(i.rate(), 96000, rate_quantum=320, quality=50)

    def integrate(r):
        out = np.empty_like(r)
        sum = 0.0
        for i, v in enumerate(r):
            sum += v
            out[i] = sum
        return out
    
    while True:
        samples = i.read(i.rate())
        if samples is None:
            break
        samples = samples[0]
        
        
        #
        # Now set up a linear scale that stretches these captured samples
        # into the time region between the timecode points.
        #
        scale = np.linspace(0, int(i.rate()), len(samples)+1)[1:]

        flutter = np.sin(np.linspace(0, 2*np.pi*1.0, len(samples))) * .05
        speed = integrate(flutter)

        #
        # Incorporate the flutter measurements into the scale.
        #
        scale -= speed
            
        #
        # Try an experiment: samples need to be amplified by inverse of
        # speed.
        #
        samples = samples * np.reciprocal(1.0 + flutter)

        out = sr.process(samples, scale)
        w.write(out.reshape((1, len(out))))

    w.close()
