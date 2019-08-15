from __future__ import print_function
import numpy as np
import sys
import getopt
import jdsp.io.WaveSink
import struct
from jdsp.blocks import ScalableResampler, ToneFollower, HighPassFilter
from jdsp.util import DelayBuffer
from irig_b import IRIGBDecoder
from collections import namedtuple
from itertools import izip

#
# A track to be respeeded. Consists of a sample source, a resampler,
# and a sample sink.
#
Track = namedtuple('Track', 'source resampler sink')

#
# A respeed block. Tells how to respeed a particular block of samples.
#
RespeedBlock = namedtuple('RespeedBlock', 'start_sample timing')

#
# On disk representation of the header of a respeed block.
#
RespeedBlockHeaderStruct = struct.Struct('QI')

#
# Trace file header.
#
TraceHeader = namedtuple('TraceHeader',
    'ident version endian_check start_sample')

#
# On-disk representation of trace header.
#
TraceHeaderStruct = struct.Struct('4sIQQ')

def CheckTraceFile(f):
    h = f.read(TraceHeaderStruct.size)

    if len(h) != TraceHeaderStruct.size:
        raise Exception('Trace file header too short.')

    header = TraceHeader(*TraceHeaderStruct.unpack(h))

    if header.ident != 'dflt':
        raise Exception('Trace file has bad magic number.')
    if header.version != 1:
        raise Exception('Incompatible trace header version.')
    if header.endian_check != 0x0001020304050607:
        raise Exception('Trace file endianess not native!')

    return header

def GetRespeedBlock(f):
    '''Read the next respeed block from a trace file.
    
    Returns None if EOF.
    '''
    b = f.read(RespeedBlockHeaderStruct.size)
    if b is None:
        return b
    if len(b) < RespeedBlockHeaderStruct.size:
        return None
    start_sample, timing_len = RespeedBlockHeaderStruct.unpack(b)
    timing = np.fromfile(f, dtype=np.float32, count=timing_len)
    return RespeedBlock(start_sample, timing)

def RespeedBlocksFromFile(f):
    '''
    Iterator. Yields respeed indications from a trace file.
    '''
    header = CheckTraceFile(f)

    if header.start_sample != 0:
        yield 'skip', header.start_sample

    while True:
        b = GetRespeedBlock(f)
        if b is None:
            raise StopIteration()
        yield 'rspd', b

def RespeedBlocksFromTimecode(tc_source, prescale, skip, check_overflow,
    block_size, deflutter_depth):
    '''
    Iterator. Yields respeed directions from an IRIG-B timecode WAV.
    '''
    queued_frames = []
    last_frame = None

    #
    # Set up a function to receive decoded timecode frames.
    #
    def frame_received(f):
        queued_frames.append(f)

    tc_follower = ToneFollower(tc_source.rate(), 1000, 200, 28)
    tc_decoder = IRIGBDecoder(tc_source.rate(), frame_received)

    #
    # Construct a high-pass filter for denoising timecode samples.
    # Use a 5 millisecond window.
    #
    five_ms_samples = int(tc_source.rate() * 0.005)
    if (five_ms_samples % 2) == 0:
        five_ms_samples += 1

    tc_hp = HighPassFilter(tc_source.rate(), five_ms_samples, 400.0)

    #
    # Figure out what kind of delays our processing system is going to
    # incur so that we can process the right audio with the right
    # speed measurements.
    #
    timecode_delay = tc_hp.delay()
    pll_delay = tc_follower.delay()

    #
    # Phase buffer, for global de-fluttering.
    #
    tc_phase_buf = DelayBuffer(delay=pll_delay, zero_stuff=False)

    total_samples = 0

    #
    # All respeed sessions can optionally start with a 'skip to'
    # sample offset command.
    #
    # If we've been told to skip, process it here.
    #
    if skip > 0:
        #
        # Skip to the required point in the timecode.
        #
        while total_samples < start_sample:
            block_read_size = min(start_sample - total_samples, 100000)
            tc_source.read(block_read_size)
            total_samples += block_read_size

        #
        # Tell the timecode decoder about the offset.
        #
        tc_decoder.set_start_sample(skip)

        #
        # Yield a skip command so that the caller will do the same to
        # its consumers.
        #
        yield 'skip', skip

    done = False
    while not done:
        tc_samples = tc_source.read(block_size)

        if tc_samples is None:
            #
            # Tell decoder and PLL that we're done.
            #
            tc_decoder.process(tc_hp.done())
            tc_decoder.done()
            tc_phase_buf.add(tc_follower.done())
            done = True
        else:
            tc_samples = tc_samples[0]

            #
            # Feed to IRIG-B processor for frames.
            #
            tc_decoder.process(tc_hp.process(tc_samples*prescale))

            #
            # Feed to IRIG-B PLL tracker for wow and flutter.
            #
            tc_phase_buf.add(tc_follower.process(tc_samples))

        #
        # See if the timecode decoder has found something.
        #
        while queued_frames:
            #
            # Examine head frame information from queue.
            #
            frame = queued_frames[0]

            #
            # Do we have a previous frame?
            #
            if last_frame is None:
                #
                # Don't have last frame yet, this is the first detected frame.
                # Don't attempt to deflutter any audio up to this point. Just
                # save it as is.
                #
                start_sample = skip
                rescale = False
            else:
                start_sample = last_frame.absolute_sample
                rescale = True

            #
            # Consult PLL to see if it has the required speed information
            # about the discovered frame.
            #
            samples = frame.absolute_sample - start_sample
            have_speed = tc_phase_buf.have(start_sample - skip, samples) == 1
            if not have_speed:
                #
                # We don't yet have the phasing information for this region.
                # Keep collecting and processing.
                #
                break

            #
            # Determine the rescaling to attempt.
            #
            if not rescale:
                scale = np.linspace(0, samples, samples+1)[1:]
            else:
                #
                # We've got frame data. We now know about a definitive region
                # which should be timed to exactly some integer seconds long.
                #
                # First, determine the number of desired samples between the
                # timecode frames. This is simply the sample rate times the
                # timecode differences, in seconds.
                #
                seconds = float(samples) / tc_source.rate()
                nominal_seconds = np.rint(seconds)
                desired_samples = nominal_seconds * tc_source.rate()

                #
                # Fetch the measured flutter in this region of samples.
                #
                playback_speed = tc_phase_buf.get(start_sample - skip, samples)
                tc_phase_buf.consume(start_sample - skip, samples)
                resample_speed = np.reciprocal(playback_speed)

                #
                # Subtract the overall average out of the speed vector. This
                # will ensure that the sum of all the flutter information between
                # these two timecode points will be zero, allowing us to
                # incorporate the fact that we know the timecode into the result.
                #
                resample_speed = resample_speed - np.average(resample_speed)

                #
                # Convert the flutter rate into a time function.
                #
                deflutter = integrate(resample_speed) * deflutter_depth

                #
                # Now set up a linear scale that stretches these captured
                # samples into the time region between the timecode points.
                #
                scale = np.linspace(0, desired_samples, samples+1)[1:]

                #
                # Incorporate the flutter measurements into the scale.
                #
                scale -= deflutter

            #
            # Construct and yield the timing block.
            #
            block = RespeedBlock(
                start_sample=start_sample,
                timing=scale
            )
            yield 'rspd',block

            #
            # Try next frame.
            #
            last_frame = frame
            queued_frames.pop(0)


        #
        # Update samples reader.
        #
        total_samples += block_size

        #
        # Check if there appears to be a problem with the timecode.
        #
        if check_overflow is not None:
            if last_frame is None:
                target = skip + check_overflow
            else:
                target = last_frame.absolute_sample + check_overflow

            if total_samples > check_overflow:
                seconds = check_overflow // tc_source.rate()
                print('Input overflow. More than %d seconds without timecode'
                    % seconds, file=sys.stderr)
                done = True

def InitializeTraceFile(f, skip):
    header = TraceHeader(
        ident='dflt',
        version=1,
        endian_check=0x0001020304050607,
        start_sample=skip
    )

    f.write(TraceHeaderStruct.pack(*header))

def DumpRespeedBlock(f, rs):
    '''Dump a respeed block to a file.'''
    f.write(RespeedBlockHeaderStruct.pack(rs.start_sample, len(rs.timing)))
    rs.timing.astype(dtype=np.float32).tofile(f)

def integrate(r):
    out = np.empty_like(r)
    sum = 0.0
    for i, v in enumerate(r):
        sum += v
        out[i] = sum
    return out

def usage(prog, code, msg=None):
    if msg is not None:
        print(msg, file=sys.stderr)
    s = \
    'Deflutter and dewow audio recordings.\n' \
    'usage: {prog} timecode [options] [<audio-files>]\n' \
    '   or: {prog} trace [options] <audio-files>\n' \
    '\n' \
    '   timecode -- Process IRIG-B timecode to generate deflutter trace.\n' \
    '   trace    -- Use existing deflutter trace to process other audio.\n' \
    '\n' \
    '   TIMECODE MODE\n' \
    '\n' \
    '   In timecode processing mode, the tape flutter and wow are extracted\n' \
    '   from an IRIG-B audio track. The flutter measurements can then be\n' \
    '   applied immediately to other audio tracks, or they can be saved\n' \
    '   to a trace file, where they can be loaded and used for a later job.\n' \
    '\n' \
    '   timecode [-f <max-idle>] [-i] [-s <offset>]\n' \
    '       [-d <depth>] [-o <trace-data-out>] [-t <timecode-audio-out>]\n' \
    '       <timecode-audio-in> [<audio-file-1-in> <audio-file-1-out>]\n' \
    '       [<audio-file-2-in> <audio-file-2-out>] ...\n' \
    '\n' \
    '    -i\n' \
    '        Invert IRIG-B signal before decoding.\n' \
    '\n' \
    '    -s <offset>\n' \
    '        Skip <offset> seconds from start of file. This will change\n' \
    '        the use of any trace file written, so be wise and remember\n' \
    '        the offset used when loading any such trace file!\n' \
    '\n' \
    '    -d <depth>\n' \
    '        (No longer necessary) De-flutter depth. Scale the respeed\n' \
    '        vector by <depth> before applying it to the audio to be\n' \
    '        resampled. (floating point)\n' \
    '\n' \
    '    -f <max-idle>\n' \
    '        Stop processing if more than <max-idle> seconds elapse\n' \
    '        without any detected timecode frames. (floating point)\n' \
    '\n' \
    '    -t <timecode-audio-out>\n' \
    '        Deflutter the timecode track and write and write it to\n' \
    '        <timecode-audio-out>.\n' \
    '\n' \
    '   TRACE MODE\n' \
    '\n' \
    '   In trace processing mode, the tape flutter and wow are loaded from\n' \
    '   from a previously-created trace file and then applied to other\n' \
    '   tracks.\n' \
    '\n' \
    '   trace <trace-data-file>\n' \
    '       <audio-file-1-in> <audio-file-1-out>\n' \
    '       [<audio-file-2-in> <audio-file-2-out>]\n' \
    '\n' \
    ''.format(prog=prog)
    print(s, file=sys.stderr)
    sys.exit(code)

def main(prog, args):
    prog, args = sys.argv[0], sys.argv[1:]

    if len(args) < 1:
        usage(prog, 1, 'Need mode.')

    verb, args = args[0].lower(), args[1:]

    if verb == 'timecode':
        do_timecode_input(prog, args)
    elif verb == 'trace':
        do_trace_input(prog, args)
    else:
        usage(prog, 1, 'Unknown verb {}'.format(verb))

def do_timecode_input(prog, args):
    block_size = 50000
    start_sample = 0
    deflutter_depth = 1
    outrate = 32000
    skip = 0
    check_overflow = None
    prescale = 1
    timecode_out_path = None
    trace_out = None

    opts, args = getopt.getopt(args, 'f:is:d:t:o:h')
    for opt, val in opts:
        if opt == '-i':
            prescale = -1
        elif opt == '-f':
            check_overflow = float(val)
        elif opt == '-s':
            skip = float(val)
        elif opt == '-d':
            deflutter_depth = float(val)
        elif opt == '-t':
            timecode_out_path = val
        elif opt == '-o':
            trace_out = open(val, 'wb')
        elif opt == '-h':
            usage(prog, 0)

    if len(args) < 1:
        usage(prog, 1, 'Need timecode input audio file.')

    tc_source_path, args = args[0], args[1:]
    tc_source = jdsp.io.WaveSource(tc_source_path)

    #
    # Compute the starting sample number.
    #
    start_sample = skip * tc_source.rate()

    #
    # Compute the sample count threshold for the timecode dead check.
    #
    if check_overflow is not None:
        check_overflow = check_overflow * tc_source.rate()

    #
    # Set up the trace output file, if directed.
    #
    if trace_out is not None:
        InitializeTraceFile(trace_out, skip)

    #
    # Set up all the input audio tracks.
    #
    tracks = []

    #
    # If the timecode itself should be respeeded, add it as a track.
    #
    if timecode_out_path is not None:
        s = jdsp.io.WaveSource(tc_source_path)
        o = jdsp.io.WaveSink(timecode_out_path, outrate, 1, 2)
        rs = ScalableResampler(s.rate(), outrate, speed_quantum=320,
            quality=50)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    #
    # Add in the tracks to be processed.
    #
    for i in range(0, len(args), 2):
        s = jdsp.io.WaveSource(args[i])
        o = jdsp.io.WaveSink(args[i+1], outrate, 1, 2)
        rs = ScalableResampler(s.rate(), outrate, speed_quantum=320,
            quality=50)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    total_samples = 0

    for cmd, arg in \
        RespeedBlocksFromTimecode(tc_source, prescale, skip, check_overflow,
            block_size, deflutter_depth):

        #
        # If writing a trace output file, examine and possibly dump this
        # block.
        #
        if trace_out is not None:
            if cmd == 'skip':
                # Skip command should already be part of the trace header.
                # Just check sanity here.
                assert(total_samples == 0)
                assert(arg == skip)
            elif cmd == 'rspd':
                print(arg.start_sample, len(arg.timing))
                DumpRespeedBlock(trace_out, arg)

        #
        # Now process any other audio tracks with the block.
        #
        total_samples = respeed_tracks(total_samples, cmd, arg, tracks)

    #
    # Session is all done. Wrap things up.
    #
    if trace_out is not None:
        trace_out.close()

    for track in tracks:
        out = track.resampler.done()
        track.sink.write(out.reshape((1, len(out))))
        track.sink.close()

def do_trace_input(prog, args):
    '''
    Trace input mode. Take an existing trace and apply it to other tracks.
    '''
    outrate = 32000

    opts, args = getopt.getopt(args, 'h')
    for opt, val in opts:
        if opt == '-h':
            usage(prog, 0)

    if len(args) < 1:
        usage(prog, 1, 'Need trace input file.')

    #
    # Open the trace file, check it, and prepare to read directions
    # from it.
    #
    trace_path, args = args[0], args[1:]
    trace = open(trace_path, 'rb')
    block_source = iter(RespeedBlocksFromFile(trace))

    #
    # Set up all the input audio tracks.
    #
    tracks = []

    for i in range(0, len(args), 2):
        s = jdsp.io.WaveSource(args[i])
        o = jdsp.io.WaveSink(args[i+1], outrate, 1, 2)
        rs = ScalableResampler(s.rate(), outrate, speed_quantum=320,
            quality=50)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    total_samples = 0

    for cmd, arg in block_source:
        #
        # Respeed any tracks that are along for the ride.
        #
        if cmd == 'rspd':
            print(arg.start_sample, len(arg.timing))
        elif cmd == 'skip':
            print(0, arg)
        total_samples = respeed_tracks(total_samples, cmd, arg, tracks)

    #
    # Session is all done. Wrap things up.
    #
    for track in tracks:
        out = track.resampler.done()
        track.sink.write(out.reshape((1, len(out))))
        track.sink.close()

def respeed_tracks(total_samples, cmd, arg, tracks):
    if cmd == 'skip':
        #
        # Skip command. Argument is sample count.
        #
        start_sample = arg

        #
        # There should only be one skip command, and it should be at
        # the file start.
        #
        assert(total_samples == 0)

        #
        # Fast forward each input track to the desired spot.
        #
        for track in tracks:
            track_total = 0
            while track_total_samples < start_sample:
                block_read_size = min(start_sample - track_total, 100000)
                track.source.read(block_read_size)
                track_total += block_read_size

        #
        # Update global sample count.
        #
        total_samples = start_sample
    elif cmd == 'rspd':
        #
        # Respeed command. Argument is a respeed block.
        #
        block = arg

        #
        # Check sanity of the respeeding stream and our current position.
        #
        assert(block.start_sample == total_samples)

        #
        # Read in the data for this block from all sources.
        #
        block_size = len(block.timing)

        #
        # Process all the associated tracks.
        #
        for track in tracks:
            audio = track.source.read(block_size)[0]
            out = track.resampler.process(audio, block.timing)
            track.sink.write(out.reshape((1, len(out))))

        total_samples += block_size
    else:
        raise Exception('Unknown internal command.')

    return total_samples

if __name__ == '__main__':
    main(sys.argv[0], sys.argv[1:])
