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
Purpose - To generate inspectable traces of flutter measurements to learn
what bandwidth is generally needed to represent it.
'''
import sys
from jdsp.io import WaveSink, WaveSource
from jdsp.blocks import ToneFollowerPC

try:
    tc_source_path = sys.argv[1]
except:
    print >>sys.stderr, "usage: ft <timecode-wav>"
    sys.exit(1)

tc_source = WaveSource(tc_source_path)
tc_carrier = open('tc_carrier.raw', 'wb')
tc_rate = open('tc_rate.raw', 'wb')
tc_follower = ToneFollowerPC(tc_source.rate(), 1000, 300, 28)

block_size = 16000
done = False
while not done:
    #
    # Read the next chunk of timecode audio.
    #
    tc_samples = tc_source.read(block_size)

    if tc_samples is None:
        break

    rate, carrier = tc_follower.process(tc_samples[0])
    tc_rate.write(rate.tobytes())
    tc_carrier.write(carrier.tobytes())
