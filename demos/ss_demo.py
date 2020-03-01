#!/usr/bin/env python
#
# Copyright 2020 Jeremy Cooper.
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
'''
Purpose - To warp a modern song with the same flutter 
what bandwidth is generally needed to represent it.
'''
from __future__ import print_function
import numpy
from jdsp.blocks import ScalableResampler
from jdsp.io import WaveSink, WaveSource

astley_wav = '/Users/jeremy/Desktop/StarSpangled.wav'
astley_out_wav = '/Users/jeremy/Desktop/StarMangled.wav' 
a13_t708_flutter = '/Users/jeremy/src/git/Apollo_Audio_Processing/processing_scripts/tc_rate.raw'
flutter_start = int((159912 / 16000.0) * 48000.0)
average_check_samples = int(48000 * 60.0)

astley_in = WaveSource(astley_wav)
assert(astley_in.rate() == 48000.0)

#
# Process stereo input, two resamplers required.
#
rsL = ScalableResampler(astley_in.rate(), astley_in.rate(),
    speed_quantum=320,
    quality=50
)
rsR = ScalableResampler(astley_in.rate(), astley_in.rate(),
    speed_quantum=320,
    quality=50
)

flutter_f = open(a13_t708_flutter, 'rb')
flutter_f.read(flutter_start * 8) # skip
flutter_b = flutter_f.read(average_check_samples * 8)
flutter = numpy.frombuffer(flutter_b, dtype=numpy.float64)
average_rate = numpy.average(flutter)
flutter_f.close()

flutter_f = open(a13_t708_flutter, 'rb')
flutter_f.read(flutter_start * 8) # skip

sink = WaveSink(astley_out_wav, astley_in.rate(), 2, 2)
block_size = 4800
i = 0

while True:
    audio = astley_in.read(block_size)
    
    if audio is None:
        break

    alen = len(audio[0])
    flutter_b = flutter_f.read(alen * 8)
    rate_r = numpy.frombuffer(flutter_b, dtype=numpy.float64)
    rate = rate_r - average_rate
    rate += 1.0
    timing = numpy.cumsum(rate)

    outL = rsL.process(audio[0], timing)
    outR = rsR.process(audio[1], timing)

    out = numpy.empty((2, len(outL)), dtype=numpy.float)
    out[0] = outL
    out[1] = outR
    
    sink.write(out)

sink.close()
