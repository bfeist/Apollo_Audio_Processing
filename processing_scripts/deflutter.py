from __future__ import print_function
import numpy as np
import sys
import getopt
import jdsp.io.WaveSink
from jdsp.blocks import ScalableResampler, ToneFollower, HighPassFilter
from irig_b import IRIGBDecoder
from collections import namedtuple
from itertools import izip

Track = namedtuple('Track', 'source buffer resampler sink')

queued_frames = []
last_frame = None

def frame_received(f):
    queued_frames.append(f)

def integrate(r):
    out = np.empty_like(r)
    sum = 0.0
    for i, v in enumerate(r):
        sum += v
        out[i] = sum
    return out

class DelayBuffer(object):
    def __init__(self, delay=0, zero_stuff=True):
        self.sample_number = -delay
        self.buffer = np.empty(1000, dtype='float')
        self.count = 0
        self.size = 1000
        if zero_stuff and delay != 0:
            self.add(np.zeros(delay, dtype='float'))

    def add(self, samples):
        l = len(samples)
        if l + self.count > self.size:
            newsize = self.size + l
            newbuffer = np.empty(newsize, dtype='float')
            newbuffer[:self.count] = self.buffer[:self.count]
            self.buffer = newbuffer
            self.size = newsize
        self.buffer[self.count:self.count+l] = samples
        self.count += l

    def consume(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        assert(have == 1)
        newcount = self.count - end
        self.buffer[:newcount] = self.buffer[end:self.count]
        self.sample_number += end
        self.count = newcount

    def get(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        assert(have == 1)
        return self.buffer[off:end]

    def have(self, sample_number, count):
        have, off, end = self.find(sample_number, count)
        return have

    def find(self, sample_number, count):
        if sample_number < self.sample_number:
            # We'll never have it.
            return -1, None, None
        sample_number -= self.sample_number
        end = sample_number + count
        if end > self.count:
            # Don't have end yet
            return -2, None, None
        return 1, sample_number, end

def usage(code, msg=None):
    if msg is not None:
        print(msg, file=sys.stderr)
    s = \
    'Deflutter and dewow audio recordings using an IRIG-B track.\n' \
    'usage: {} [-f <max-buffer>] [-i] [-s <start-samp>] [-d <depth>]\n' \
    '       <timecode-audio-in> <timecode-audio-out> ' \
           '[<audio-file> [<audio-file> ...]]\n' \
    '-f -- Stop processing if more than <max-buffer> seconds elapse\n' \
    '      without any detected timecode frames.\n' \
    '-i -- Invert IRIG-B signal before decoding.\n' \
    '-d -- De-flutter depth. Needed until I discover why it needs tweaking\n' \
    '-s -- Skip <offset> seconds from start of file.\n'.format(prog)
    print(s, file=sys.stderr)
    sys.exit(code)

check_overflow = None
invert = False
block_size = 50000
start_sample = 0
deflutter_depth = 1
prescale = 1
outrate = 96000
skip = 0

prog, args = sys.argv[0], sys.argv[1:]
opts, args = getopt.getopt(args, 'f:is:d:h')
for opt, val in opts:
    if opt == '-i':
        prescale = -1
    elif opt == '-f':
        check_overflow = float(val)
    elif opt == '-s':
        skip = float(val)
    elif opt == '-d':
        print(val)
        deflutter_depth = float(val)
    elif opt == '-h':
        usage(0)

if len(args) < 2:
    usage(1, 'Need timecode file and timecode output file.')

tc_source = jdsp.io.WaveSource(args[0])
tc_sink = jdsp.io.WaveSink(args[1], outrate, 1, 2)
tc_follower = ToneFollower(tc_source.rate(), 1000, 200, 28)
tc_decoder = IRIGBDecoder(tc_source.rate(), frame_received)
tc_resampler = ScalableResampler(tc_source.rate(), outrate, quality=50)

five_ms_samples = int(tc_source.rate() * 0.005)
if (five_ms_samples % 2) == 0:
    five_ms_samples += 1

#
# High-pass filter for denoising timecode samples.
#
tc_hp = HighPassFilter(tc_source.rate(), five_ms_samples, 400.0)

timecode_delay = tc_hp.delay()
pll_delay = tc_follower.delay()

tracks = []

for i in range(2, len(args), 2):
    s = jdsp.io.WaveSource(args[i])
    o = jdsp.io.WaveSink(args[i+1], outrate, 1, 2)
    b = DelayBuffer(delay=timecode_delay, zero_stuff=False)
    rs = ScalableResampler(tc_source.rate(), outrate, quality=50)
    tracks.append(Track(source=s, sink=o, buffer=b, resampler=rs))

#
# Phase buffer, for global de-fluttering.
#
tc_phase_buf = DelayBuffer(delay=pll_delay, zero_stuff=False)

# Timecode track
tc_sample_buf = DelayBuffer(delay=timecode_delay, zero_stuff=False)

# start_sample = 130813495 # Research area of T885-19 Epoch
#   2966s
#   invert = -1
# start_sample = 279020700 # Research area of T884-18 Epoch
#   6327s
# start_sample = x # Landing area of T885-19 Epoch
#   2966s + 896s = 3862s
# invert = 1

start_sample = skip * tc_source.rate()
if check_overflow is not None:
    check_overflow_count = check_overflow * tc_source.rate()

total_samples = 0
while True:
    tc_samples = tc_source.read(block_size)
    a_samples = [ track.source.read(block_size)[0] for track in tracks ]

    if tc_samples is None:
        break

    tc_samples = tc_samples[0]
    
    if total_samples < start_sample:
        total_samples += len(tc_samples)
        continue

    #
    # Store in recall buffer.
    #
    tc_sample_buf.add(tc_samples)
    
    #
    # Feed to IRIG-B processor for frames.
    #
    tc_decoder.process(tc_hp.process(tc_samples*prescale))

    #
    # Feed to IRIG-B PLL tracker for wow and flutter.
    #
    pll = tc_follower.process(tc_samples)
    tc_phase_buf.add(pll)
    
    #
    # Load audio data from associated audio tracks.
    #
    for tsamples, track in izip(a_samples, tracks):
        track.buffer.add(tsamples)
    
    #
    # Work through servicable frames.
    #
    while True:
        if not queued_frames:
            break
        
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
            last_frame_sample_number = 0
            rescale = False
        else:
            last_frame_sample_number = last_frame.absolute_sample
            rescale = True
        
        #
        # Consult all buffers to see if they are ready.
        #
        samples = frame.absolute_sample - last_frame_sample_number
        tc_have = tc_sample_buf.have(last_frame_sample_number, samples) == 1 \
                  and tc_phase_buf.have(last_frame_sample_number, samples) == 1
        
        ab_haves = True
        for track in tracks:
            t_have = track.buffer.have(last_frame_sample_number, samples) == 1
            ab_haves = ab_haves and t_have
        
        if not tc_have or not ab_haves:
            # We can't service this information yet. Keep collecting
            # samples.
            break
        
        #
        # Determine the rescaling to attempt.
        #
        if not rescale:
            # Keep this section unscaled. Write as is.
            scale = np.linspace(0, samples, samples+1)[1:]
        else:
            #
            # We've got frame data. Deflutter the audio between samples
            # using what we know.
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
            playback_speed = tc_phase_buf.get(last_frame_sample_number, samples)
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
            # Now set up a linear scale that stretches these captured samples
            # into the time region between the timecode points.
            #
            scale = np.linspace(0, desired_samples, samples+1)[1:]
            
            #
            # Incorporate the flutter measurements into the scale.
            #
            scale -= deflutter
        
        print(last_frame_sample_number, samples)
        
        #
        # Process and deflutter the timecode track
        #
        tcaudio = tc_sample_buf.get(last_frame_sample_number, samples)
        tcout = tc_resampler.process(tcaudio, scale)
        tc_sink.write(tcout.reshape((1, len(tcout))))
        
        
        #
        # Process all the associated tracks.
        #
        for track in tracks:
            audio = track.buffer.get(last_frame_sample_number, samples)
            out = track.resampler.process(audio, scale)
            track.sink.write(out.reshape((1, len(out))))
            track.buffer.consume(last_frame_sample_number, samples)

        #
        # Update timecode buffers.
        #
        tc_phase_buf.consume(last_frame_sample_number, samples)
        tc_sample_buf.consume(last_frame_sample_number, samples)
        
        last_frame = frame
        
        #
        # Try next frame.
        #
        queued_frames.pop(0)
    
    if check_overflow is not None:
        if tc_sample_buf.count > check_overflow_count:
            print('Input overflow. More than %d seconds without timecode'
                % check_overflow, file=sys.stderr)
            break
    
tc_sink.close()
tc_source.close()

for track in tracks:
    track.source.close()
    track.sink.close()
