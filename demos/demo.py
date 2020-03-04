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
Purpose - To warp a modern song with the same flutter as Apollo 13, T708.
'''
from __future__ import print_function
import numpy
from jdsp.blocks import ScalableResampler
from jdsp.io import WaveSink, WaveSource
import sys
import argparse

a13_t708_flutter = 'tc_rate.raw'
flutter_start_s = 159912 / 16000.0
average_check_s = 60.0

parser = argparse.ArgumentParser(
    description='Flutter a sound like a MOCR Apollo tape.'
)
parser.add_argument('-s', '--flatrate',
    help="Keep overall playback rate by adjusting flutter average"
    " to 100%.",
    action="store_true"
)
parser.add_argument('-w', '--waffle', type=int, default=0, metavar='COUNT',
    help="Demonstrate the flutter by transitioning back and forth "
    "between no flutter and full flutter COUNT times in the recording."
)
parser.add_argument('in_sound', metavar='input.wav', type=str,
    help='The WAV file to flutter.'
)
parser.add_argument('out_sound', metavar='output.wav', type=str,
    help='The output file to produce.'
)

args = parser.parse_args()

input_wav = args.in_sound
output_wav = args.out_sound

audio_in = WaveSource(input_wav)
audio_length = audio_in._w.getnframes()
assert(audio_in.rate() == 48000.0)

flutter_start_samples = int(flutter_start_s * audio_in.rate())
average_check_samples = int(audio_in.rate() * average_check_s)

#
# Process stereo input, two resamplers required.
#
resamplers = [
    ScalableResampler(audio_in.rate(), audio_in.rate(),
        speed_quantum=320,
        quality=50
    ) for i in range(audio_in.channels())
]

if args.flatrate:
    flutter_f = open(a13_t708_flutter, 'rb')
    flutter_f.read(flutter_start_samples * 8) # skip
    flutter_b = flutter_f.read(average_check_samples * 8)
    flutter = numpy.frombuffer(flutter_b, dtype=numpy.float64)
    average_rate = numpy.average(flutter)
    flutter_f.close()
else:
    average_rate = 1.0

flutter_f = open(a13_t708_flutter, 'rb')
flutter_f.read(flutter_start_samples * 8) # skip
flutter_b = flutter_f.read(audio_length * 8)
flutter = numpy.frombuffer(flutter_b, dtype=numpy.float64)

if args.waffle > 0:
    steps = args.waffle * 4
    warp_step = audio_length / steps
    warp_function = numpy.empty(audio_length, dtype=numpy.float64)
    for i in range(steps):
        warp_start = i * warp_step
        warp_stop = warp_start + warp_step
        if i % 4 == 0:
            # flat here
            f = numpy.ones(warp_step, dtype=numpy.float64)
        elif i % 4 == 1:
            # transition from flat to fully fluttered
            f = numpy.linspace(1.0, 0.0, num=warp_step, dtype=numpy.float64)
        elif i % 4 == 2:
            # fully fluttered here
            f = numpy.zeros(warp_step, dtype=numpy.float64)
        elif i % 4 == 3:
            # transition from fully fluttered to flat
            f = numpy.linspace(0.0, 1.0, num=warp_step, dtype=numpy.float64)
        warp_function[warp_start:warp_stop] = f
    if warp_step * steps < audio_length:
        warp_function[warp_step*steps:audio_length] = 0.0
else:
    warp_function = numpy.zeros(audio_length, dtype=numpy.float64)

sink = WaveSink(output_wav, audio_in.rate(), audio_in.channels(),
    audio_in.depth())

block_size = 1600
i = 0

while True:
    audio = audio_in.read(block_size)
    
    if audio is None:
        break

    alen = len(audio[0])

    flutter_i = flutter[i:i+alen]
    warp = warp_function[i:i+alen]

    #
    # Apply the warping function, which dictates how the flutter
    # should mix between none and full.
    #
    rate_r = flutter_i * (1.0 - warp)
    rate_r += warp

    #
    # If there should be a different average rate, apply it here.
    #
    rate = rate_r - average_rate
    rate += 1.0
    
    #
    # Finally, convert the rate to a timing schedule, which is the format
    # needed by the resampler.
    #
    timing = numpy.cumsum(1.0 / rate)

    #
    # Prepare the output matrix.
    #
    out = numpy.empty(
        (audio_in.channels(), resamplers[0].output_possible(timing)),
        dtype=numpy.float
    )

    #
    # Resample each channel of the input, in turn.
    #
    for j, resampler in enumerate(resamplers):
        out[j] = resamplers[j].process(audio[j], timing)

    sink.write(out)

    i += alen

out = numpy.empty(
    (audio_in.channels(), resamplers[0].output_possible(None))
)
for i, r in enumerate(resamplers):
    r.done(out=out[i])

sink.write(out)
sink.close()
