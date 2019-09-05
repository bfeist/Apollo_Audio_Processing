from __future__ import print_function
import numpy as np
import sys
import getopt
import struct
import os
import time
from jdsp.blocks import ScalableResampler, ToneFollower, HighPassFilter
from jdsp.util import DelayBuffer
from jdsp.io import WaveSink, WaveSource
from irig_b import IRIGBDecoder, AbsoluteSample
from collections import namedtuple
from itertools import izip
from functools import partial
stderr = sys.stderr

#
# A track to be respeeded. Consists of a sample source, a resampler,
# and a sample sink.
#
Track = namedtuple('Track', 'source resampler sink')

#
# A respeed block. Tells how to respeed a particular block of samples.
#
RespeedBlock = namedtuple('RespeedBlock', 'start_sample timing timecode')

#
# A warning block. Warns that the respeed seems unusual. Only emitted from
# timecode sources.
#
WarningBlock = namedtuple('WarningBlock', 'start_sample rate timecode')

#
# On disk representation of the header of a respeed block.
#
RespeedBlockHeaderStruct = struct.Struct('QI')

#
# Trace file header.
#
TraceHeaderV1 = namedtuple('TraceHeaderV1',
    'ident version endian_check start_sample')
TraceHeaderV2Addition = namedtuple('TraceHeaderV2Addition',
    'input_sample_rate comment_size')

#
# Combined abstract representation.
#
TraceHeader = namedtuple('TraceHeader',
    'ident version endian_check start_sample input_sample_rate comment')

#
# On-disk representation of trace header.
#
TraceHeaderV1Struct = struct.Struct('4sIQQ')
TraceHeaderV2AdditionStruct = struct.Struct('QQ')
# For ease of writing V2 structures, only:
TraceHeaderV2Struct = struct.Struct('4sIQQQQ')

#
# Broadcast Audio Extention chunk from Broadcast Wave specificaiton.
# 2.3 Broadcast Audio Extension Chunk.
#
BWF_Audio_Extension = namedtuple('BWF_Audio_Extension',
    'Description Originator OriginatorReference OriginationDate '
    'OriginationTime TimeReferenceLow TimeReferenceHigh Version '
    'UMID LoudnessValue LoudnessRange MaxTruePeakLevel '
    'MaxMomentaryLoudness MaxShortTermLoudness Reserved '
    'CodingHistory'
)
BWF_Audio_Extension_struct = struct.Struct('<256s32s32s10s8sIIH64sHHHHH180s')

def BWFData_from_bytes(b):
    assert(len(b) >= BWF_Audio_Extension_struct.size)
    fixed_part = b[:BWF_Audio_Extension_struct.size]
    fields = list(BWF_Audio_Extension_struct.unpack(fixed_part))
    coding_history = b[BWF_Audio_Extension_struct.size:].rstrip('\x00')
    fields.append(coding_history)

    return BWF_Audio_Extension(*fields)

def BWFData_to_bytes(bwf):
    mandatory = BWF_Audio_Extension_struct.pack(*(bwf[:15]))
    pad = '\x00' if len(bwf.CodingHistory) % 2 == 1 else ''
    return mandatory + bwf.CodingHistory + pad

def ReadTraceHeaderFromFile(f):
    h = f.read(TraceHeaderV1Struct.size)

    if len(h) != TraceHeaderV1Struct.size:
        raise Exception('Trace file header too short.')

    headerv1 = TraceHeaderV1(*TraceHeaderV1Struct.unpack(h))

    if headerv1.ident != 'dflt':
        raise Exception('Trace file has bad magic number.')
    if headerv1.version > 2:
        raise Exception('Incompatible trace header version.')
    if headerv1.endian_check != 0x0001020304050607:
        raise Exception('Trace file endianess not native!')

    if headerv1.version == 2:
        a = f.read(TraceHeaderV2AdditionStruct.size)
        if len(a) != TraceHeaderV2AdditionStruct.size:
            raise Exception('Trace extension header too short.')
        addition = TraceHeaderV2Addition(*TraceHeaderV2AdditionStruct.unpack(a))
        cmt = f.read(addition.comment_size)
        if len(cmt) != addition.comment_size:
            raise Exception('Trace extension comment too short.')
        comment = cmt.decode('utf-8')
        input_sample_rate = addition.input_sample_rate
    else:
        comment = None
        input_sample_rate = None

    header = TraceHeader(
        ident=headerv1.ident,
        version=headerv1.version,
        endian_check=headerv1.endian_check,
        start_sample=headerv1.start_sample,
        input_sample_rate=input_sample_rate,
        comment=comment
    )

    return header

def GetRespeedBlock(f):
    '''
    Read the next respeed block from a trace file.
    
    Returns None if EOF.
    '''
    b = f.read(RespeedBlockHeaderStruct.size)
    if b is None:
        return b
    if len(b) < RespeedBlockHeaderStruct.size:
        return None
    start_sample, timing_len = RespeedBlockHeaderStruct.unpack(b)
    timing = np.fromfile(f, dtype=np.float32, count=timing_len)
    return RespeedBlock(start_sample, timing, None)

def RespeedBlocksFromFile(header, f):
    '''
    Iterator. Yields respeed indications from a trace file.
    '''
    if header.start_sample != 0:
        yield 'skip', header.start_sample

    while True:
        b = GetRespeedBlock(f)
        if b is None:
            raise StopIteration()
        yield 'rspd', b

def RespeedBlocksFromTimecode(tc_source, prescale, skip, check_overflow,
    block_size, deflutter_depth, do_high_pass_filtering, do_frame_filtering):
    '''
    Iterator. Yields respeed directions from an IRIG-B timecode WAV.
    '''
    queued_commands = []
    last_frame = None

    if do_frame_filtering:
        #
        # To correct long-term drift of the signal we use IRIG-B frame
        # start markers as indicators of the long-term drift. But in bad
        # signals this can cause short-term jitter if an IRIG-B frame is
        # detected where one shouldn't be.
        #
        # With this option turned on, we will only consider good frames
        # when attempting to correct long-term drift. But since IRIG-B doesn't
        # have any built-in error correction schemes, the way to detect
        # bad frames is to rely on some heuristics and other redundancies.
        #
        # For now, this means only accepting a frame as valid and usable if its
        # SBS field checks out against its HH:MM:SS field.
        #
        frame_filter = lambda frame: frame.ok_sbs_tm
    else:
        #
        # Don't filter any frames.
        #
        frame_filter = lambda frame: True

    #
    # Set up a function to receive decoded timecode frames.
    #
    def frame_received(f):
        if frame_filter(f):
            queued_commands.append(f)

    tc_follower = ToneFollower(tc_source.rate(), 1000, 300, 28)
    tc_decoder = IRIGBDecoder(tc_source.rate(), frame_received)

    #
    # Set up timecode audio preprocessing.
    #
    if do_high_pass_filtering:
        #
        # Construct a high-pass filter for denoising timecode samples.
        #
        # We'll use a 400 Hz high pass filter with enough taps to cover
        # 5 milliseconds of time.
        #
        window_samples = int(tc_source.rate() * 0.005)
        if (window_samples % 2) == 0:
            window_samples += 1

        tc_hp = HighPassFilter(tc_source.rate(), window_samples, 400.0)
        timecode_delay = tc_hp.delay()

        preprocess = lambda samples: tc_hp.process(samples*prescale)
        preprocess_done = lambda: tc_hp.done()
    else:
        preprocess = lambda samples: samples*prescale
        preprocess_done = lambda: np.empty(0, dtype='float')
        timecode_delay = 0

    #
    # Figure out what kind of delays our processing system is going to
    # incur so that we can process the right audio with the right
    # speed measurements.
    #
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
        tc_source._w.setpos(skip)
        total_samples += skip

        #
        # Yield a skip command so that the caller will do the same to
        # its consumers.
        #
        yield 'skip', skip

    #
    # Tell the timecode decoder about the offset as well as the
    # high-pass filter delay.
    #
    tc_decoder.set_sample_number(skip-timecode_delay)

    done = False
    while not done:
        #
        # Read the next chunk of timecode audio.
        #
        tc_samples = tc_source.read(block_size)

        if tc_samples is None:
            #
            # We've reached the end of the timecode audio.
            # Tell decoder and PLL that we're done.
            #
            tc_decoder.process(preprocess_done())
            tc_phase_buf.add(tc_follower.done())

            #
            # Put a 'stop frame' into the processing queue, ensuring that
            # the remaining audio (if any) is simply copied as is to the
            # output.
            #
            queued_commands.append(None)
            done = True
        else:
            tc_samples = tc_samples[0]

            #
            # Feed to IRIG-B processor for frames.
            #
            tc_decoder.process(preprocess(tc_samples))

            #
            # Feed to IRIG-B PLL tracker for wow and flutter.
            #
            tc_phase_buf.add(tc_follower.process(tc_samples))

            #
            # Update samples read.
            #
            total_samples += len(tc_samples)

        #
        # See if the timecode decoder has found something and/or if there
        # are any processing commands queued.
        #
        while queued_commands:
            #
            # Examine head frame information from queue.
            #
            frame = queued_commands[0]

            #
            # Do we have a previous frame?
            #
            if last_frame is None:
                #
                # Don't have last frame yet, this is the first detected frame.
                # Start from the skip point (if any).
                #
                start_sample = AbsoluteSample(skip, 0)
            else:
                #
                # We have a previous frame. Start from there.
                #
                start_sample = last_frame.absolute_sample

            if frame is not None:
                #
                # This is the start of a detected IRIG-B frame.
                # Its start sample is where we should stop this resample
                # chunk.
                #
                end_sample = frame.absolute_sample

                #
                # If we have a previous good decode frame, then this is a
                # region we should rescale and deflutter. If not, we should
                # just copy the chunk as is.
                #
                rescale = last_frame is not None
                time_sync = rescale
            else:
                #
                # This is a stop processing command. Deflutter the remaining
                # audio just using the PLL information. Don't try to time
                # sync.
                #
                end_sample = AbsoluteSample(total_samples, 0)
                rescale = True
                time_sync = False

            #
            # Consult PLL to see if it has the required speed information
            # about the discovered frame.
            #
            samples = end_sample.i - start_sample.i
            have_speed = tc_phase_buf.have(start_sample.i - skip, samples) == 1
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
                #
                # No rescaling required.
                #
                scale = np.linspace(0, samples, samples+1)[1:]
            else:
                #
                # Fetch the measured speed in this region of samples
                # (according to the IRIG-B carrier signal).
                #
                # Measured speed will be a per-sample ratio a/b, where a
                # is the measured speed and b is the desired speed.
                #
                carrier_speed = tc_phase_buf.get(start_sample.i-skip, samples)

                if time_sync:
                    #
                    # We've got frame data. We now know about a definitive
                    # region which should be timed to exactly some integer
                    # seconds long.
                    #
                    # First, determine the number of desired samples between
                    # the timecode frames. This is simply the sample rate times
                    # the timecode differences, in seconds.
                    #
                    seconds = float(samples) / tc_source.rate()
                    nominal_seconds = np.rint(seconds)
                    desired_samples = nominal_seconds * tc_source.rate()

                    #
                    # Incorporate the fractional zero-crossing times of the
                    # two frames involved here to derive the precise sample
                    # distance between the their start times.
                    #
                    zc_distance_samples = samples + \
                        end_sample.f - start_sample.f
                    
                    #
                    # Compute the detected playback speed (as a ratio relative
                    # the ideal speed) as measured by the distance between the
                    # timecode sync points.
                    #
                    tc_speed = float(desired_samples) / zc_distance_samples 

                    #
                    # Put some checks in place.
                    #
                    if tc_speed < 0.8 or tc_speed > 1.25:
                        #
                        # The new measured playback rate exceeds the bounds
                        # 80%-%125 (4/5 - 5/4), which is likely a sign that,
                        # perhaps, this IRIG-B code point is a fluke.
                        #
                        # Yield a warning upstream, and then just skip trying
                        # to integrate this frame marker. Hopefully the next
                        # one we receive should be ok.
                        #
                        yield 'warn', WarningBlock(start_sample.i, overall_rate,
                            frame)

                        #
                        # Throw away this marker and continue.
                        #
                        queued_commands.pop(0)
                        continue

                    #
                    # Subtract the overall average out of the speed vector.
                    # This will ensure that the sum of all the flutter
                    # information between these two timecode points will be
                    # zero, allowing us to incorporate the fact that we know
                    # the timecode into the result.
                    #
                    flutter_speed = carrier_speed - np.average(carrier_speed)

                    #
                    # Adjust the flutter depth now, if requested.
                    #
                    flutter_speed *= deflutter_depth

                    #
                    # Insert the detected timecode rate required to
                    # ensure that the selected samples will occupy some exact
                    # integer number of seconds of playback.
                    #
                    correction_speed = flutter_speed + tc_speed

                    #
                    # Convert the desired playback rate into a time function.
                    #
                    scale = np.cumsum(correction_speed)
                else:
                    scale = np.cumsum(carrier_speed)

                #
                # Mark the phase samples as safe to destroy.
                #
                tc_phase_buf.consume(start_sample.i - skip, samples)

            #
            # Construct and yield the timing block.
            #
            block = RespeedBlock(
                start_sample=start_sample.i,
                timing=scale,
                timecode=frame
            )
            yield 'rspd',block

            #
            # Try next frame.
            #
            queued_commands.pop(0)
            last_frame = frame

        #
        # Check if there appears to be a problem with the timecode.
        #
        if check_overflow is not None:
            if last_frame is None:
                target = skip + check_overflow
            else:
                target = last_frame.absolute_sample.i + check_overflow

            if total_samples > target:
                seconds = check_overflow // tc_source.rate()
                print('Input overflow. More than %d seconds without timecode.'
                    % seconds, file=sys.stderr)
                print('Stopping at',
                    samples_to_time(tc_source.rate(), total_samples),
                    file=sys.stderr)

                #
                # Push a stop signal onto the frame queue.
                #
                queued_frames.append(None)

def InitializeTraceFile(f, skip, input_sample_rate, comment):
    header = TraceHeader(
        ident='dflt',
        version=2,
        endian_check=0x0001020304050607,
        start_sample=skip,
        input_sample_rate=input_sample_rate,
        comment=comment.encode('utf-8')
    )

    f.write(TraceHeaderV2Struct.pack(
        header.ident,
        header.version,
        header.endian_check,
        header.start_sample,
        header.input_sample_rate,
        len(header.comment)
    ))

    f.write(header.comment)

def DumpRespeedBlock(f, rs):
    '''Dump a respeed block to a file.'''
    f.write(RespeedBlockHeaderStruct.pack(rs.start_sample, len(rs.timing)))
    rs.timing.astype(dtype=np.float32).tofile(f)

def usage(prog, code, verb=None, msg=None):
    if msg is not None:
        print(msg, file=sys.stderr)

    if verb is None:
        do_timecode = True
        do_trace = True
    elif verb == 'timecode':
        do_timecode = True
        do_trace = False
    elif verb == 'trace':
        do_timecode = False
        do_trace = True
    else:
        raise Exception('Programmer error in help function!')

    common = \
    'Deflutter and dewow audio recordings.\n'
    'usage: {prog} timecode [options] [<audio-files>]\n' \
    '   or: {prog} trace [options] <audio-files>\n' \
    '\n' \
    '   timecode -- Process IRIG-B timecode to generate deflutter trace.\n' \
    '   trace    -- Use existing deflutter trace to process other audio.\n' \
    '\n'.format(prog=prog)

    timecode = \
    '   TIMECODE MODE\n' \
    '\n' \
    '   In timecode processing mode, the tape flutter and wow are extracted\n' \
    '   from an IRIG-B audio track. The flutter measurements can then be\n' \
    '   applied immediately to other audio tracks, or they can be saved\n' \
    '   to a trace file, where they can be loaded and used for a later job.\n' \
    '\n' \
    '   timecode [-f <max-idle>] [-i] [-s <offset>] [-r <outrate>]\n' \
    '       [-d <depth>] [-o <trace-data-out>] [-t <timecode-audio-out>]\n' \
    '       [-T <version-tag>] [-q <quality>] [-Q <respeed-quantum>]\n' \
    '       [-F] [-m]\n' \
    '       <timecode-audio-in> [<audio-file-1-in> <audio-file-1-out>]\n' \
    '       [<audio-file-2-in> <audio-file-2-out>] ...\n' \
    '\n' \
    '    -i\n' \
    '        Invert IRIG-B signal before decoding.\n' \
    '\n' \
    '    -F\n' \
    '        Apply a 400 Hertz high-pass filter to the timecode before\n' \
    '        decoding.\n' \
    '\n' \
    '    -m\n' \
    '        Apply error checking to IRIG-B signal to avoid locking on to\n' \
    '        noise and inducing jitter. A frames will be checked to ensure\n' \
    '        that its Straight-Binary-Seconds field matches its HH:MM:SS\n' \
    '        field before being accepted.\n' \
    '\n' \
    '    -s <offset>\n' \
    '        Skip <offset> seconds from start of file. This will change\n' \
    '        the use of any trace file written, so be wise and remember\n' \
    '        the offset used when loading any such trace file!\n' \
    '\n' \
    '    -d <depth>\n' \
    '        (No longer necessary) De-flutter depth. Scale the respeed\n' \
    '        vector by <depth> before applying it to the audio to be\n' \
    '        resampled. (floating point) (default: 1.0)\n' \
    '\n' \
    '    -f <max-idle>\n' \
    '        Stop processing if more than <max-idle> seconds elapse\n' \
    '        without any detected timecode frames. (floating point)\n' \
    '\n' \
    '    -t <timecode-audio-out>\n' \
    '        Deflutter the timecode track and write and write it to\n' \
    '        <timecode-audio-out>.\n' \
    '\n' \
    '    -T <version-tag>\n' \
    '        When updating the Broadcast Wave meta-data in the output, use\n' \
    '        <version-tag> as the tool version number in the Coding\n' \
    '        History (default "Unknown version").\n' \
    '\n' \
    '   The following options are only valid when processing additional audio\n' \
    '   files with the timecode:\n' \
    '\n' \
    '    -r <outrate>\n' \
    '        Convert each defluttered output file to sample rate <outrate>,\n' \
    '        hertz. (Default: 16000).\n' \
    '\n' \
    '    -q <quality>\n' \
    '        Use a Sinc window size of <quality> input samples when\n' \
    '        constructing the deflutter resampler. (Default: 50).\n' \
    '\n' \
    '    -Q <respeed-quantum>\n' \
    '        When defluttering and respeeding input audio, the algorithm\n' \
    '        ultimately determines the corrected playback rate of each input\n' \
    '        sample. For efficiency, this rate is rounded to the nearest\n' \
    '        integer value k, in the expression  k / Q. The higher\n' \
    '        the value of Q (the respeed quantum), the more resolution the\n' \
    '        will be available to the resampler in placing the respeeded\n' \
    '        sample in the correct place during playback. (Default: 320)\n' \
    '\n'

    trace = \
    '   TRACE MODE\n' \
    '\n' \
    '   In trace processing mode, the tape flutter and wow are loaded from\n' \
    '   from a previously-created trace file and then applied to other\n' \
    '   tracks.\n' \
    '\n' \
    '   trace\n' \
    '       [-T <version-tag>] [-r <outrate>] [-q <quality>]\n' \
    '       [-Q <respeed-quantum>]\n' \
    '       <trace-data-file>\n' \
    '       <audio-file-1-in> <audio-file-1-out>\n' \
    '       [<audio-file-2-in> <audio-file-2-out>]\n' \
    '\n' \
    '    -r <outrate>\n' \
    '        Convert each defluttered output file to sample rate <outrate>,\n' \
    '        hertz. (Default: 16000).\n' \
    '\n' \
    '    -q <quality>\n' \
    '        Use a Sinc window size of <quality> input samples when\n' \
    '        constructing the deflutter resampler. (Default: 50).\n' \
    '\n' \
    '    -Q <respeed-quantum>\n' \
    '        When defluttering and respeeding input audio, the algorithm\n' \
    '        ultimately determines the corrected playback rate of each input\n' \
    '        sample. For efficiency, this rate is rounded to the nearest\n' \
    '        integer value k, in the expression  k / Q. The higher\n' \
    '        the value of Q (the respeed quantum), the more resolution the\n' \
    '        will be available to the resampler in placing the respeeded\n' \
    '        sample in the correct place during playback. (Default: 320)\n' \

    '    -T <version-tag>\n' \
    '        When updating the Broadcast Wave meta-data in the output, use\n' \
    '        <version-tag> as the tool version number in the Coding\n' \
    '        History (default "Unknown version").\n' \
    '\n'

    print(common, file=sys.stderr)

    if do_timecode:
        print(timecode, file=sys.stderr)

    if do_trace:
        print(trace, file=sys.stderr)

    sys.exit(code)

def samples_to_time(rate, n):
    seconds = float(n) / rate
    h = int(seconds // 3600)
    m = int((seconds // 60) % 60)
    s = seconds % 60
    return '{:03d}:{:02d}:{:06.3f}'.format(h, m, s)

def progress_report(total, inrate, outrate, cmd, arg, written):
    if cmd is None:
        #
        # We're done.
        #
        print('')
        print('Done.')
        return
    elif cmd == 'rspd':
        start_sample_number = arg.start_sample
        samples_read = len(arg.timing)
        #
        # The "argument" of this respeed block is the timing vector
        # Gather some statistics.
        #
        rate = arg.timing[1:] - arg.timing[:-1]
        speed_max = np.max(rate)
        speed_min = np.min(rate)
        speed_avg = np.average(rate)
        timecode = arg.timecode
    else:
        start_sample_number = 0
        samples_read = arg
        speed_max = 1.0
        speed_min = 1.0
        speed_avg = 1.0
        timecode = None

    if timecode is not None:
        timecode = 'IRIG-B {:03d}:{:02d}:{:02d}:{:02d}'.format(
            timecode.days,
            timecode.hours,
            timecode.minutes,
            timecode.seconds
        )

    in_time = samples_to_time(inrate, start_sample_number)

    done = float(start_sample_number) / float(total)

    print(
        in_time,
        '{:04.1f}%'.format(done * 100.0),
        'respeed {:5.3f}/{:5.3f}/{:5.3f}'.format(
            speed_min, speed_avg, speed_max
        ),
        timecode,
        end='\r',
        file=stderr
    )

    return samples_read

def fn_escape(fn):
    '''
    Insert escape sequences in a filename to make it meta-data suitable.
    '''
    fn = fn.replace('%', '%25')
    fn = fn.replace(' ', '%20')
    fn = fn.replace(',', '%2C')
    return fn.replace(';', '%3B')

def GenerateTraceMetaData(source_path, prescale, skip, deflutter_depth,
    source_rate, do_hpf, do_frame_filter):
    '''
    Generate a history block for the tracing portion of a session.
    '''

    meta_data = \
        'TimeCodeSourceFile={SourceFile};' \
        'Prescale={Prescale};' \
        'SkipSeconds={SkipSeconds};' \
        'DeflutterDepth={DeflutterDepth};' \
        'InputSampleRate={InputSampleRate}'.format(
            SourceFile=fn_escape(os.path.split(source_path)[-1]),
            Prescale=prescale,
            SkipSeconds=skip,
            DeflutterDepth=deflutter_depth,
            InputSampleRate=source_rate
        )

    if do_hpf:
        meta_data += \
            ';' \
            'TimeCodeHighPassFilter=400Hz;' \
            'TimeCodeHighPassFilterWindow=0.005s'

    if do_frame_filter:
        meta_data += \
            ';' \
            'IRIGBFrameFilter=SBSMatchesHMS'

    return meta_data

def UpdateBWF(source, source_name, dest, dest_name, dest_rate, dest_depth,
        dest_mode, trace_meta_data, speed_quantum, quality, tag):
    '''
    Preserve and update (or create) Broadcast Wave format information.
    
    Copies over the Broadcast WAVE meta-data from source, to dest and updates
    the processing history to reflect this defluttering session.
    
    If BWF data does not exist in source, a new history will be created in
    dest.
    '''
    source_bwf_bytes = source._w.get_chunk('bext')

    now = time.time()
    date_ref = time.strftime('%Y-%m-%d', time.gmtime(now))
    time_ref = time.strftime('%H:%M:%S', time.gmtime(now))

    if source_bwf_bytes is not None:
        bwf = BWFData_from_bytes(source_bwf_bytes)
    else:
        rand_code = os.urandom(12).encode('hex')
        bwf = BWF_Audio_Extension(
            Description='Defluttered audio',
            Originator='ApolloAudioProject',
            OriginatorReference='USAaP' + rand_code,
            OriginationDate=date_ref,
            OriginationTime=time_ref,
            TimeReferenceLow=0,
            TimeReferenceHigh=0,
            Version=2,
            UMID='',
            LoudnessValue=0,
            LoudnessRange=0,
            MaxTruePeakLevel=0,
            MaxMomentaryLoudness=0,
            MaxShortTermLoudness=0,
            Reserved='',
            CodingHistory=''
        )

    resampler_meta = \
        'SourceFile={SourceFile};' \
        'RespeedQuantum={RespeedQuantum};' \
        'Quality={Quality}'.format(
        SourceFile=fn_escape(os.path.split(source_name)[-1]),
        RespeedQuantum=speed_quantum,
        Quality=quality
    )

    this_entry = \
        'A=PCM,F={SampleRate},W={depth},M={Mode},' \
        'T=Defluttered;Time={DateRef}T{TimeRef}-0000;' \
        'Tool={Tool};{TraceMetaData};{ResampleMetaData}\n'.format(
            SampleRate=dest_rate,
            depth=dest_depth,
            Mode=dest_mode,
            DateRef=date_ref,
            TimeRef=time_ref,
            Tool='deflutter.py',
            TraceMetaData=trace_meta_data,
            ResampleMetaData=resampler_meta
        )

    coding_history = bwf.CodingHistory

    new_bwf = bwf._replace(
        CodingHistory=coding_history+this_entry.encode('ascii')
    )

    bwf_bytes = BWFData_to_bytes(new_bwf)
    dest._w.add_chunk('bext', bwf_bytes)

def main(prog, args):
    prog, args = sys.argv[0], sys.argv[1:]

    if len(args) < 1:
        usage(prog, 1, None, 'Need mode.')

    verb, args = args[0].lower(), args[1:]

    if verb == 'timecode':
        do_timecode_input(prog, args)
    elif verb == 'trace':
        do_trace_input(prog, args)
    else:
        usage(prog, 1, None, 'Unknown verb {}'.format(verb))

def do_timecode_input(prog, args):
    block_size = 50000
    start_sample = 0
    deflutter_depth = 1
    outrate = 16000
    skip = 0
    check_overflow = None
    prescale = 1
    timecode_out_path = None
    trace_out = None
    additional_meta_data = None
    speed_quantum = 320
    quality = 50
    do_high_pass_filtering = False
    do_frame_filtering = False

    opts, args = getopt.getopt(args, 'Fmf:is:d:t:o:hT:r:q:Q:')
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
        elif opt == '-T':
            additional_meta_data = val
        elif opt == '-r':
            outrate = int(val)
        elif opt == '-q':
            quality = int(val)
        elif opt == '-Q':
            speed_quantum = int(val)
        elif opt == '-F':
            do_high_pass_filtering = True
        elif opt == '-m':
            do_frame_filtering = True
        elif opt == '-h':
            usage(prog, 0, 'timecode')

    if len(args) < 1:
        usage(prog, 1, 'timecode', 'Need timecode input audio file.')

    tc_source_path, args = args[0], args[1:]
    tc_source = WaveSource(tc_source_path)

    #
    # Compute the starting sample number.
    #
    start_sample = int(skip * tc_source.rate())
    total_samples = tc_source._w.getnframes() - start_sample

    #
    # Compute the sample count threshold for the timecode dead check.
    #
    if check_overflow is not None:
        check_overflow = check_overflow * tc_source.rate()

    #
    # Create a meta-data comment for all of the parameters involved.
    #
    trace_meta_data = GenerateTraceMetaData(
        tc_source_path, prescale, skip, deflutter_depth, tc_source.rate(),
        do_high_pass_filtering, do_frame_filtering
    )

    if additional_meta_data is not None:
        trace_meta_data += ';' + additional_meta_data

    #
    # Set up the trace output file, if directed.
    #
    if trace_out is not None:
        InitializeTraceFile(trace_out, skip, int(tc_source.rate()),
            trace_meta_data)

    #
    # Set up all the input audio tracks.
    #
    tracks = []

    #
    # If the timecode itself should be respeeded, add it as a track.
    #
    if timecode_out_path is not None:
        s = WaveSource(tc_source_path)
        o = WaveSink(timecode_out_path, outrate, 1, 2)

        UpdateBWF(s, tc_source_path, o, timecode_out_path, outrate, 16,
            'mono', trace_meta_data, speed_quantum, quality,
            additional_meta_data)

        rs = ScalableResampler(s.rate(), outrate, speed_quantum=speed_quantum,
            quality=quality)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    #
    # Add in the tracks to be processed.
    #
    for i in range(0, len(args), 2):
        s = WaveSource(args[i])
        o = WaveSink(args[i+1], outrate, 1, 2)

        UpdateBWF(s, args[i], o, args[i+1], outrate, 16, 'mono',
            trace_meta_data, speed_quantum, quality, additional_meta_data)

        rs = ScalableResampler(s.rate(), outrate, speed_quantum=speed_quantum,
            quality=quality)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    #
    # Set up progress meter.
    #
    progress = partial(progress_report, total_samples, tc_source.rate(),
        outrate)

    total_samples = 0

    respeed_source = iter(
        RespeedBlocksFromTimecode(tc_source, prescale, start_sample,
            check_overflow, block_size, deflutter_depth,
            do_high_pass_filtering, do_frame_filtering)
    )

    for cmd, arg in respeed_source:
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
                DumpRespeedBlock(trace_out, arg)

        #
        # Warning blocks should print a message.
        #
        if cmd == 'warn':
            when = samples_to_time(tc_source.rate(), arg.start_sample)
            print('WARNING:', 'unusual respeed rate', arg.rate, 'at', when,
                'timecode', arg.timecode)
            continue

        #
        # Now process any other audio tracks with the block.
        #
        if tracks:
            written = respeed_tracks(total_samples, cmd, arg, tracks)
        else:
            written = None

        samples_read = progress(cmd, arg, written)
        total_samples += samples_read

    #
    # Session is all done. Wrap things up.
    #
    if trace_out is not None:
        trace_out.close()

    for track in tracks:
        out = track.resampler.done()
        track.sink.write(out.reshape((1, len(out))))
        track.sink.close()

    progress(None, None, None)

def do_trace_input(prog, args):
    '''
    Trace input mode. Take an existing trace and apply it to other tracks.
    '''
    outrate = 16000
    tag = 'Version=Unknown-version'
    speed_quantum = 320
    quality = 50

    opts, args = getopt.getopt(args, 'hT:q:Q:r:')
    for opt, val in opts:
        if opt == '-h':
            usage(prog, 0, 'trace')
        elif opt == '-T':
            tag = val
        elif opt == '-r':
            outrate = int(val)
        elif opt == '-q':
            quality = int(val)
        elif opt == '-Q':
            speed_quantum = int(val)


    if len(args) < 1:
        usage(prog, 1, None, 'Need trace input file.')

    #
    # Open the trace file, check it, and prepare to read directions
    # from it.
    #
    trace_path, args = args[0], args[1:]
    trace = open(trace_path, 'rb')

    header = ReadTraceHeaderFromFile(trace)
    if header.version == 1:
        raise Exception('Not a v2 trace file')

    if len(args) <  2:
        usage(prog, 'timecode', 'Need at least one audio file to deflutter!')

    #
    # Set up all the input audio tracks.
    #
    tracks = []

    for i in range(0, len(args), 2):
        s = WaveSource(args[i])

        if int(s.rate()) != header.input_sample_rate:
            raise Exception('Trace sample rate does not match input rate.')

        o = WaveSink(args[i+1], outrate, 1, 2)

        UpdateBWF(s, args[i], o, args[i+1], outrate, 16, 'mono', header.comment,
            speed_quantum, quality, tag)

        rs = ScalableResampler(s.rate(), outrate, speed_quantum=speed_quantum,
            quality=quality)
        tracks.append(Track(source=s, resampler=rs, sink=o))

    #
    # Peek at the first source to see how many samples we expect to
    # process.
    #
    total_samples = tracks[0].source._w.getnframes()

    #
    # Set up progress meter.
    #
    progress = partial(progress_report, total_samples, s.rate(), outrate)

    samples_processed = 0

    for cmd, arg in iter(RespeedBlocksFromFile(header, trace)):
        #
        # Respeed any tracks that are along for the ride.
        #
        written = respeed_tracks(samples_processed, cmd, arg, tracks)

        read_samples = progress(cmd, arg, written)
        samples_processed += read_samples

    #
    # Session is all done. Wrap things up.
    #
    for track in tracks:
        out = track.resampler.done()
        written = len(out)
        track.sink.write(out.reshape((1, len(out))))
        track.sink.close()

    progress(None, None, written)

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
            track.source._w.setpos(start_sample)

        #
        # Update global sample count.
        #
        written = 0
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

        written = len(out)
    else:
        raise Exception('Unknown internal command.')

    return written

if __name__ == '__main__':
    main(sys.argv[0], sys.argv[1:])
