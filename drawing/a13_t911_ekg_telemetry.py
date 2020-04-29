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
from jdsp.blocks import ToneFollower, ScalableResampler
from jdsp.io import WaveSource
from collections import namedtuple
from numpy import around, cumsum, ones, rint
import json
import bisect
import math

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

def elapsed_to_str(elapsed):
    h = int(elapsed / 3600.0)
    m = int(elapsed / 60.0) % 60
    f, i = math.modf(elapsed)
    s = i % 60
    
    return '%03d:%02d:%02d.%06d' % (h, m, s, int(f * 1000000))

def parse_HMS(s):
    '''
    Convert an x:y:z tuple into total seconds.
    '''
    parts = s.split(':')
    assert(len(parts) == 3)
    parts_f = [ float(f) for f in parts ]
    return parts_f[0] * 3600.0 + parts_f[1] * 60 + parts_f[2]

def timestamps(f):
    '''
    Iterate over the data from an Adobe audition timestamp file, producing
    <filetime>, <missiontime>.
    
    Format -- <GET> <File-Time> <Duration> <timefmt> <marker-type> <note>
    '''
    for line in f:
        parts = line.split('\t')
        assert(len(parts) == 6)
        get, ft, duration, timefmt, markertyp, note = parts
        
        mission_elapsed = parse_HMS(get)
        file_elapsed = parse_HMS(ft)
        yield file_elapsed, mission_elapsed

def filetime_to_missiontime(ft, file_times, mission_times):
    '''
    Given a file position (in seconds, float), return the mission time (in
    seconds, float).
    '''
    index = bisect.bisect(file_times, ft)
    if index == 0:
        raise Exception('No mission time available for given file time.')
    delta = ft - file_times[index-1]
    return mission_times[index-1] + delta

def main(sys_args):
    import sys
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description='Process Apollo biomed telemetry')
    parser.add_argument('--skip', '-s',
        metavar='<skip-seconds>', type=float,dest='skip',
        help='Point at which to start processing, in seconds (floating point).')
    parser.add_argument('--duration', '-d',
        metavar='<duration-seconds>', type=float, dest='duration', default=60.0,
        help='Number of seconds to process (floating point, default 60).')
    parser.add_argument('--timestamps', '-t',
        metavar='<timestamp-file>', type=str, dest='timestamps', default=None,
        help='Adobe timestamp file, for meta-data preservation.')
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
    else:
        skip_frames = 0

    #
    # Ingest the timestamp file into a searchable format.
    #
    if args.timestamps is not None:
        file_times = []
        mission_times = []
        for file_time, mission_time in timestamps(open(args.timestamps, 'rt')):
            file_times.append(file_time)
            mission_times.append(mission_time)

    #
    # Configure each tone follower for the tone it is supposed to follow.
    #
    followers = [
        ToneFollower(input_rate, c.frequency, c.bandwidth, c.lpf)
        for c in channels
    ]

    #
    # Set up a group of rational resamplers to bring the outputs of each
    # channel down to the rate being asked.
    #
    resamplers = [
        ScalableResampler(int(input_rate), int(output_rate), speed_quantum=320, quality=9000)
        for c in channels
    ]

    #
    # Compute the overall delay of the whole system.
    #
    overall_delay_input = resamplers[0].delay() + followers[0].delay()
    overall_delay_output = float(overall_delay_input) / float(input_rate) * output_rate

    #
    # Find the sample number in the output which will be
    # closest to the processed input.
    #
    output_start_offset = rint(overall_delay_output)

    #
    # Compute the error that results from choosing this particular
    # sample.
    #
    output_start_res = overall_delay_output - output_start_offset
    output_start_res_s = output_start_res / float(output_rate)

    #
    # Compute the input start time that this output sample
    # actually represents.
    #
    output_input_time_s = float(skip_frames) / float(input_rate) - \
        output_start_res_s

    #
    # Convert to mission time, if possible.
    #
    if args.timestamps is not None:
        output_start_mission_s = filetime_to_missiontime(output_input_time_s,
            file_times, mission_times)
    else:
        output_start_mission_s = None

    output_offset = 0
    processed = 0

    channel_data = [ [] for channel in channels ]

    block_size = 1000
    while True:
        data = input_source.read(block_size)
        if data is None:
            break

        frames = data[0]

        #
        # Run each tone decoder on the input block.
        #
        followed = [ follower.process(frames) for follower in followers ]

        #
        # Now run the downsampler on the output of each tone decoder.
        #
        outputs = [
            resampler.process(frames, cumsum(ones(len(frames))))
            for frames, resampler in zip(followed, resamplers)
        ]

        #
        # Due to the deterministic algorithm of the resampler, the number
        # of samples produced by one resampler should be equal to the
        # number of samples produced by any other. So check the output
        # of the first resampler to determine how many output samples
        # we have produced in each channel.
        #
        output_frames = len(outputs[0])

        #
        # Determine if the processing delay has been reached.
        #
        if output_offset < output_start_offset:
            #
            # Still need to eat more output samples until the overall
            # processing delay has been removed.
            #
            available_here = (output_offset + output_frames) - output_start_offset
            output_offset += output_frames

            #
            # It's possible that the delay was just satisfied in the
            # statements above. Is there input left in this output
            # buffer?
            #
            if available_here > 0:
                #
                # Yes, we've satisfied the delay by dropping samples from
                # this buffer. The remaining samples in this buffer represent
                # the start of the output to use.
                #
                outputs = [ data[-available_here:] for data in outputs ]
                output_frames = available_here
            else:
                #
                # No, we haven't satisfied the delay yet, even after dropping
                # all of the samples in this output buffer. Keep processing.
                #
                continue

        #
        # Take the output channels one at a time, reformat their data
        # to conform with JSON requirements, and concatenate them onto
        # the result set we are producing.
        #
        for l, o in zip(channel_data, outputs):
            l += list(around(o, decimals=5))

        processed += output_frames
        if processed > process_frames:
            break

    #
    # Assemble a data dictionary with the results.
    #
    d = dict()
    for data, meta in zip(channel_data, channels):
        d[meta.name] = data

    #
    # Assemble the full result set by adding in
    # meta-data.
    #
    result = {
        'sample_rate' : output_rate,
        'source_start_time_s' : 0 if args.skip is None else float(args.skip),
        'output_source_start_time_s' : output_input_time_s,
        'source_file' : args.input,
        'channels' : d
    }
    if output_start_mission_s:
        et = elapsed_to_str(output_start_mission_s)
        result['mission_et'] = et

    print(json.dumps(result))

if __name__ == '__main__':
    import sys
    main(sys.argv)
