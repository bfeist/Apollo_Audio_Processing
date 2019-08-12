import numpy as np
from jdsp.blocks import ScalableResampler, ToneFollower, HighPassFilter
import jdsp.io.WaveSink
from irig_b import IRIGBDecoder
import sys

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
    def __init__(self, start_count=0):
        self.sample_number = start_count
        self.buffer = np.empty(1000, dtype='float')
        self.count = 0
        self.size = 1000

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

i = jdsp.io.WaveSource(sys.argv[1])
v = jdsp.io.WaveSource(sys.argv[2])
w = jdsp.io.WaveSink(sys.argv[3], 96000, 1, 2)
tw = jdsp.io.WaveSink(sys.argv[4], 96000, 1, 2)
t = ToneFollower(i.rate(), 1000, 200, 10)
sr = ScalableResampler(i.rate(), 96000)
tsr = ScalableResampler(i.rate(), 96000)

five_ms_samples = int(i.rate() * 0.005)
if (five_ms_samples % 2) == 0:
    five_ms_samples += 1

hp = HighPassFilter(i.rate(), five_ms_samples, 400.0)
tc = IRIGBDecoder(i.rate(), frame_received)

timecode_delay = hp.delay()
pll_delay = t.delay()

#
# Phase buffer, for global de-fluttering.
#
pb = DelayBuffer(-pll_delay)

# Timecode track
sb = DelayBuffer(-timecode_delay)
# Voice track
vb = DelayBuffer(-timecode_delay)

flutter_depth = 10.0

total_samples = 0
while True:
    samples = i.read(10000)
    vsamples = v.read(10000)

    if samples is None:
        break

    samples = samples[0]
    
    if total_samples < 130813495:
        total_samples += len(samples)
        continue

    #
    # Store in recall buffer.
    #
    sb.add(samples)
    vb.add(vsamples[0])
    
    #
    # Feed to IRIG-B processor for frames.
    #
    tc.process(hp.process(samples*-1.0))

    #
    # Feed to IRIG-B PLL tracker for wow and flutter.
    #
    pll = t.process(samples)
    pb.add(pll)
    
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
        sb_have = sb.have(last_frame_sample_number, samples)
        pb_have = pb.have(last_frame_sample_number, samples)

        if sb_have != 1 or pb_have != 1:
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
            seconds = float(samples) / i.rate()
            nominal_seconds = np.rint(seconds)
            desired_samples = nominal_seconds * i.rate()
            
            #
            # Fetch the measured flutter in this region of samples.
            #
            speed = pb.get(last_frame_sample_number, samples) * flutter_depth
            

            #
            # Subtract the overall average out of the speed vector. This
            # will ensure that the sum of all the flutter information between
            # these two timecode points will be zero, allowing us to
            # incorporate the fact that we know the timecode into the result.
            #
            speed = speed - np.average(speed)
            
            #
            # Convert the flutter rate into a time function.
            #
            flutter = integrate(speed)

            #
            # Now set up a linear scale that stretches these captured samples
            # into the time region between the timecode points.
            #
            scale = np.linspace(0, desired_samples, samples+1)[1:]
            
            #
            # Incorporate the flutter measurements into the scale.
            #
            scale -= flutter
        
        print last_frame_sample_number, samples
        
        #
        # Fetch the audio being processed.
        #
        audio = vb.get(last_frame_sample_number, samples)
        tcaudio = sb.get(last_frame_sample_number, samples)
        
        out = sr.process(audio, scale)
        tcout = tsr.process(tcaudio, scale)
        w.write(out.reshape((1, len(out))))
        tw.write(tcout.reshape((1, len(tcout))))
        sb.consume(last_frame_sample_number, samples)
        vb.consume(last_frame_sample_number, samples)
        pb.consume(last_frame_sample_number, samples)
        
        last_frame = frame
        
        #
        # Try next frame.
        #
        queued_frames.pop(0)
    
w.close()
