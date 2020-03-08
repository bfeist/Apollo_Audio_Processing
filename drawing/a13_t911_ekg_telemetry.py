'''
Astronaut bio-medical telemetry decoding for Apollo missions.

Accidental telemetry exported to Apollo 13 MOCR audio tapes, discovered by
Jeremy Cooper on 2019-08-21 on tape T911, channel 13, at GET 032:37:07 /
1970-04-14 03:50:01 GMT.

This system is described in AS-508 "MCC/MSFN MISSION CONFIGURATION/SYSTEM
DESCRIPTION". On page 52 of that document there is a table that reads:

IRIG Channel No.   Measurement Name
1                  Unassigned
2                  Command Module Pilot's ZPN
3                  Commander's ZPN
4                  Lunar Module Piolt's ZPN
5                  Commander's EKG
6                  Command Module Pilot's EKG
7                  LM Pilot's EKG

The instruments that made these measurements appear to be described in detail
in the NASA document: https://history.nasa.gov/SP-368/s6ch3.htm

A "ZPN" is a "one impedance pneumograph", or a spring-like device that
measures an astronaut's chest movements, and hence, their breathing patterns.

'''
from __future__ import print_function
from jdsp.blocks import ToneFollower, RationalResampler
from jdsp.io import WaveSource
from collections import namedtuple
from numpy import around
import json

FMTelemetryChannel = namedtuple('FMTelemetryChannel',
    'name frequency bandwidth lpf')

#
# These frequencies were worked out by hand by observing spectrograms
# of the audio snippet we have.
#
channels = [
    FMTelemetryChannel(name='CMP ZPN',frequency=550.0,bandwidth=100.0,lpf=15),
    FMTelemetryChannel(name='CMDR ZPN',frequency=725.0,bandwidth=100.0,lpf=15),
    FMTelemetryChannel(name='LMP ZPN',frequency=950.0,bandwidth=100.0,lpf=15),
    FMTelemetryChannel(name='CMDR EKG',frequency=1300.0,bandwidth=200.0,lpf=15),
    FMTelemetryChannel(name='CMP EKG',frequency=1700.0,bandwidth=200.0,lpf=15),
    FMTelemetryChannel(name='LMP EKG',frequency=2300.0,bandwidth=200.0,lpf=15)
]

def main(sys_args):
    import sys
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description='Process Apollo biomed telemetry')
    parser.add_argument('--skip', '-s', metavar='<skip-seconds>', type=float,
        dest='skip',
        help='Point at which to start processing, in seconds (floating point).')
    parser.add_argument('--duration', '-d', metavar='<duration-seconds>',
        type=float, dest='duration', default=60.0,
        help='Number of seconds to process (floating point, default 60).')
    parser.add_argument('input', metavar='<input-wav>', type=str,
                        help='Audio file for input.')
    parser.add_argument('rate', metavar='<output-rate>', type=float, default=60,
        nargs='?', help='Output sample rate (Hz, float, default=60).'
    )

    args = parser.parse_args(sys_args[1:])

    input_source = WaveSource(args.input)
    if input_source.channels() != 1:
        print("Input must be monophonic (single channel).", file=sys.stderr)
        sys.exit(1)

    input_rate = input_source.rate()
    output_rate = args.rate
    process_frames = int(output_rate * args.duration)

    if args.skip is not None:
        skip_frames = input_rate * args.skip
        input_source.set_position(skip_frames)

    #
    # Configure each tone follower for the tone it is supposed to follow.
    #
    followers = [
        ToneFollower(input_rate, c.frequency, c.bandwidth, c.lpf)
        for c in channels
    ]

    #
    # Set up a rational resampler to bring the output down to the rate
    # being asked.
    #
    resamplers = [
        RationalResampler(int(input_rate), int(output_rate), quality=9000)
        for c in channels
    ]

    #
    # Compute the overall delay of the whole system.
    #
    overall_delay_input = resamplers[0].delay() + followers[0].delay()
    overall_delay_output = overall_delay_input / input_rate * output_rate
    delayed = 0
    processed = 0

    channel_data = [ [] for channel in channels ]

    block_size = 1000
    while True:
        data = input_source.read(block_size)
        if data is None:
            break

        frames = data[0]

        outputs = [
            resampler.process(follower.process(frames))
            for follower, resampler in zip(followers, resamplers)
        ]

        output_frames = len(outputs[0])

        #
        # Determine if the processing delay has been reached.
        #
        if delayed < overall_delay_output:
            available_here = (delayed + output_frames) - overall_delay_output
            delayed += output_frames
            if available_here > 0:
                outputs = [ data[-available_here:] for data in outputs ]
                output_frames = available_here
            else:
                # Keep processing, haven't reached start output.
                continue

        for l, o in zip(channel_data, outputs):
            l += list(around(o, decimals=5))

        processed += output_frames
        if processed > process_frames:
            break

    #
    # Assemble a data dictionary with the results.
    #
    d = {}
    for data, meta in zip(channel_data, channels):
        d[meta.name] = data

    print(json.dumps(d))

if __name__ == '__main__':
    import sys
    main(sys.argv)
