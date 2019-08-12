#!/usr/bin/env python
from math import exp, sqrt, log, pow, sin, cos, pi, atan
import numpy
import collections

IRIGBFrame = collections.namedtuple('IRIGBFrame',
    'seconds minutes hours days years control sbs')

def nasa_time(f):
    total_hours = f.hours + (f.days + (f.years * 365)) * 24
    return '%02d:%02d:%2d' % (total_hours, f.minutes, f.seconds)

class PLL(object):
    def __init__(self, rate, freq, eval_cycles, alpha):
        self.phase = 0.0
        self.incr = 2 * pi * freq / rate
        self.clamp_max = self.incr * 1.01
        self.clamp_min = self.incr * 0.99
        self.alpha = alpha
        self.eval_cycles = eval_cycles
        self.cycle = 0
        self.sumI = 0.0
        self.sumQ = 0.0
        
    def process(self, data):
        twopi = 2 * pi
        left = len(data)
        i = 0
        outphase = numpy.empty((3, left), dtype='float')
        while left > 0:
            phasor = numpy.arange(self.phase, twopi, self.incr)
            if len(phasor) > left:
                phasor = phasor[0:left]
            part = data[i:i+len(phasor)]
            outphase[0,i:i+len(phasor)] = numpy.sin(phasor)
            outphase[1,i:i+len(phasor)] = numpy.sin(phasor) * part
            outphase[2,i:i+len(phasor)] = numpy.cos(phasor) * part
            self.sumI += numpy.dot(part, numpy.sin(phasor))
            self.sumQ += numpy.dot(part, numpy.cos(phasor))
            self.phase = phasor[-1] + self.incr
            i += len(phasor)
            left -= len(phasor)
            #
            # Have we completed a full cycle of the oscillator?
            #
            if self.phase >= twopi:
                #
                # Full cycle completed. Keep angle sane.
                #
                self.phase -= twopi
                
                #
                # Is it time to evaluate the error?
                #
                self.cycle += 1
                if self.cycle >= self.eval_cycles:
                    #
                    # Time to evaluate the PLL error.
                    #
                    error_angle = self.measure_error(self.sumI, self.sumQ)
                    self.incr += error_angle * self.alpha
                    self.cycles = 0
                    self.sumI, self.sumQ = 0.0, 0.0
                    self.incr = max(self.clamp_min, self.incr)
                    self.incr = min(self.clamp_max, self.incr)
        return outphase

    @staticmethod
    def measure_error(I, Q):
        if I == 0.0:
            err_angle = (pi/2.0) if Q > 0.0 else (-pi/2.0)
        else:
            err_angle = atan(Q / I)
            if I < 0.0:
                err_angle += pi if Q > 0.0 else -pi
        return err_angle

class EnvelopeFollower(object):
    '''Calculates the instantaneous power envelope of a waveform using classical
    attack and release time parameters.'''
    
    def __init__(self, rate, windowSec, attackSec, releaseSec):
        '''Initializes and configures envelope detector.

        See configure() for parameters.'''
        self.configure(rate, windowSec, attackSec, releaseSec)

    def configure(self, rate, windowSec, attackSec, releaseSec):
        '''Configures detector for given parameters.

        rate - Input sample rate, in hertz.
        windowSec - The size of the evaluation window, in seconds.
        attackSec - Attack rate, in seconds.
        releaseSec - Release rate, in seconds.

        Attack and release rates are the measured times it takes for the
        difference between the follower's estimation of the input envelope and
        the actual input envelope to reach within negative one neper
        (about -4.3 dB) of the input envelope.

        The attack rate is used whenever the current estimation is below the
        input and the release rate is used whenever the current estimation is
        above the input.'''
     
        # Compute the attack coefficient.
        self._ga = exp(-1/(rate*attackSec))
        # and the release coefficient.
        self._gr = exp(-1/(rate*releaseSec))
        self._windowSz = int(windowSec * rate)
        self.reset()

    def reset(self):
        self._hist = numpy.zeros(self._windowSz, dtype='float')
        self._hist_i = 0
        self._envelope = 0.0

    def process(self, data):
        '''Calculate the instantaneous power envelope for the given array
        of input data, returning an output array of envelope values the
        same size.

        The values returned are power-scaled, not voltage scaled. Thus, if
        the input waveform has an RMS power of -10 dBfs, returns 0.01 and
        not 0.0316. 0.316 would be the equivalent RMS voltage for the same
        signal.'''
        # Square each input sample and then rescale for the evaluation
        # window size. 
        data = data * data
        data = data / self._windowSz

        # Allocate the output array.
        ret = numpy.empty(len(data), dtype='float')

        # Cache some data that will be heavily used in the loop
        ga = self._ga
        gr = self._gr
        j = self._hist_i
        n = self._windowSz
        hist = self._hist
        sum = numpy.sum(self._hist)
        env = self._envelope

        for i, sample in enumerate(data):
            sum += sample
            sum -= hist[(j + i) % n]
            hist[(j + i) % n] = sample
            if env < sum:
                env *= ga
                env += (1 - ga) * sum
            else:
                env *= gr
                env += (1 - gr) * sum
            ret[i] = env

        self._envelope = env
        self._hist_i += len(data)
        self._hist_i %= n

        return ret

class AGC(object):
    '''Automatic gain controller. Tries to keep audio energy constant.'''

    def __init__(self, rate, window, attack, release, level):
        '''Instantiate an RMS-sensitive audio expander.
        
        rate - Sample rate, in hertz.
        window - RMS averaging window size, in seconds.
        attack - Attack time, in seconds. (Neper scale).
        release - Release time, in seconds. (Neper scale).
        level - Desired output level, in dBfs (fs = "full scale", where
        full-scale is assumed to be a sample value of 1.0).'''
        self._detector = EnvelopeFollower(rate, window, attack, release)
        self._target = pow(10.0, level / 10.0)

    def process(self, data):
        '''Apply automatic gain to samples.

        data - A buffer of samples to process.'''
        envelope = self._detector.process(data)
        envelope = numpy.maximum(envelope, 0.1) # Prevent zeros.
        gain = numpy.reciprocal(envelope) / self._target
        return data * gain

class IRIGBDecoder(object):
    '''An IRIG-B decoder.'''

    def __init__(self, rate, dbg, receiver):
        '''Instantiate an IRIG-B decoder for a given sample rate.

        rate - Sampling rate, in hertz.
        receiver - Callable to receive decoded frames.'''
        #assert((rate % 1000) == 0)

        self._pll = PLL(rate, 1000.0, 2, 0.5)
        self._agc = AGC(
            rate,                 # sample rate
            0.1,                  # RMS window time (seconds)
            1.0,                  # Attack time (neper basis)
            1.0,                  # Release time (neper basis)
            -10.0                 # Desired average power level, dbFS.
        )
        self._samples_per_symbol = int(rate / 1000)
        self._sync_window = numpy.zeros(self._samples_per_symbol,
            dtype='float')
        self._pos = 0
        self._sync_pos = 0
        self._evaluate_pos = self._samples_per_symbol / 2
        self._next_evaluate_pos = self._evaluate_pos
        self._sample_number = 0
        self._clock_detected = False
        self._dbg = dbg
        
    def process(self, data):
        '''Decode the given data, returning frames found, if any.'''
        # data = self._agc.process(data)
        dbg_out = numpy.empty((4, len(data)), dtype='float')
        pll = self._pll.process(data)
        dbg_out[0] = data
        dbg_out[1] = pll[0]
        dbg_out[2] = pll[1]
        dbg_out[3] = pll[2]
#        for i, sample in enumerate(data):
#            avg, synced = self.sample_now(sample)
#            dbg_out[0,i] = avg
#            dbg_out[1,i] = sample
#            if synced:
#                abs_sample = i + self._sample_number
#                self.receive_sample(abs_sample, sample)
        self._sample_number += len(data)
        self._dbg.write(dbg_out)
    
    def sample_now(self, sample):
        v = self._sync_window[self._pos]
        v *= 0.99
        v += sample * 0.01
        self._sync_window[self._pos] = v
        
        if self._pos == self._sync_pos:
            sync_now = True
            self._evaluate_pos = self._next_evaluate_pos
        else:
            sync_now = False
        
        if self._pos == self._evaluate_pos:
            maxI = numpy.argmax(self._sync_window)
            minI = numpy.argmin(self._sync_window)
            if maxI != self._sync_pos:
                self._sync_pos = maxI
                self._next_evaluate_pos = \
                    (maxI + self._samples_per_symbol / 2) % \
                    self._samples_per_symbol
            big, small = self._sync_window[[maxI, minI]]
            if big - small > 0.1:
                self._clock_detected = True
            else:
                self._clock_detected = False
                
        self._pos = (self._pos + 1) % self._samples_per_symbol
        return v, (sync_now and self._clock_detected)
    
    def receive_sample(self, abs_s, sample):
        print abs_s, sample

def gcd(x, y):
    if y > x:
        x, y = y, x
    while True:
        resid = x % y
        if resid == 0:
            return y
        else:
            x, y = y, resid

class Nothing(object):
    def __init__(self):
        pass
    
    def process(data):
        return data

class SimpleResampler(object):
    def __init__(self, in_rate, out_rate):
        assert(out_rate > in_rate)
        g = gcd(out_rate, in_rate)
        self.top = out_rate / g
        self.step = in_rate / g
        self.z = None
        self.have_z = False
        self.have_zp1 = False
        self.delta = 0
        self.cur = 0
    
    def process(self, data):
        dlen = len(data)
        i = 0
        z = self.z
        out = []
        have_z = self.have_z
        have_zp1 = self.have_zp1
        delta = self.delta
        cur = self.cur
        step = self.step
        top = self.top
        while i < dlen:
            if not have_z:
                z = data[i]
                have_z = True
                have_zp1 = False
                i += 1
                continue
            elif not have_zp1 and cur > 0:
                delta = data[i] - z
                have_zp1 = True
            out.append(z + delta * (cur / top))
            cur += step
            if cur >= top:
                cur -= top
                have_z = False
        self.z = z
        self.delta = delta
        self.have_z = have_z
        self.have_zp1 = have_zp1
        self.cur = cur
        return numpy.array(out, dtype='float')

def main(args):
  import getopt
  import wave

  class WaveSource(object):
    def __init__(self, path):
      self._w = wave.open(path, 'r')
      self._rate = self._w.getframerate()
      self._channels = self._w.getnchannels()
      self._depth = self._w.getsampwidth()

    def rate(self):
      return self._rate

    def channels(self):
      return self._channels

    def depth(self):
      return self._depth

    def read(self, frame_count):
      '''Read next available samples from file.

      Returned data will be a numpy float multi-dimensional array.
      The first dimension of the array is the channel number. The second
      dimension is the sample number in the stream.

      All sample data is normalized to a dBfs value of 1.0, regardless of
      the input sample size.

      May return less frames than requested. If no input is available, returns
      None.'''
      data = self._w.readframes(frame_count)
      if data == '':
        return None

      channels = self._channels
      depth = self._depth
      frame_count = len(data) / channels / depth

      if depth == 1:
        samples = numpy.fromstring(data, dtype=numpy.int8)
        samples = samples.reshape((channels, frame_count), order='F')
        samples = samples / float(0x80)
      elif depth == 2:
        samples = numpy.fromstring(data, dtype=numpy.uint8)
        samples = samples.astype(numpy.int16)
        samples = (samples[1::2] << 8) + \
                  (samples[0::2]     )
        samples = samples.reshape((channels, frame_count), order='F')
        samples = samples / float(0x8000)
      else:
        assert(depth == 3)
        samples = numpy.fromstring(data, dtype=numpy.uint8)
        samples = samples.astype(numpy.int32)
        samples = (samples[2::3] << 24) + \
                  (samples[1::3] << 16) + \
                  (samples[0::3] << 8)
        samples = samples.reshape((channels, frame_count), order='F')
        samples = samples / float(0x80000000)

      return samples

  class WaveSink(object):
    def __init__(self, path, rate, channels, depth):
      '''Opens a WAVe file for writing.

      path - Pathname of file to write.
      rate - Sample rate, in hertz.
      channels - Number of channels.
      depth - Number of bytes per sample (1 = 8-bit, 2 = 16-bit, 3 = 24-bit )'''
      self._channels = channels
      self._depth = depth
      self._w = wave.open(path, 'w')
      self._w.setnchannels(channels)
      self._w.setframerate(rate)
      self._w.setsampwidth(depth)

    def write(self, frames):
      '''Writes samples to file.

      frames - An array of arrays containing sample data in float format.
               The outer array must contain one entry per channel. The inner
               array contains the sample data for that channel.  Values
               will be interpreted as 1.0 being 0 dBfs.'''
      framecount = len(frames[0])
      data = frames.reshape(self._channels*framecount, order='F')
      if self._depth == 1:
        data = (data * 0x80).clip(-0x80, 0x7f).astype(numpy.int8)
        data =  ''.join([chr(x) for x in data])
      elif self._depth == 2:
        data = (data * 0x8000).clip(-0x8000, 0x7fff).astype(numpy.int16)
        out = numpy.empty(2*framecount*self._channels, dtype=numpy.uint8)
        out[1::2] = (data >> 8) & 0xff
        out[0::2] = (data     ) & 0xff
        data = ''.join([chr(x) for x in out])
      else:
        assert(self._depth == 3)
        data = (data * 0x800000).clip(-0x800000, 0x7fffff).astype(numpy.int32)
        out = numpy.empty(3*framecount*self._channels, dtype=numpy.uint8)
        out[2::3] = (data >> 16) & 0xff
        out[1::3] = (data >>  8) & 0xff
        out[0::3] = (data      ) & 0xff
        data = ''.join([chr(x) for x in out])
      self._w.writeframes(data)

    def close(self):
      self._w.close()

  def usage(prog):
    print >>sys.stderr, 'usage:', prog, '<wav-file> <debug-file>'
    sys.exit(1)

  def error(msg, code):
    print >>sys.stderr, msg
    sys.exit(code)

  def fatal(msg):
    raise Exception(msg)

  prog = args[0]
  args = args[1:]
  neper_attack_time = 0.050
  neper_release_time = 0.050
  level_dbfs = -10.0
  
  if len(args) < 2:
    usage(prog)

  in_file, dbg_file = args[0], args[1]

  try:
    src = WaveSource(in_file)
  except:
    error('Can\'t open input file', 2)

  rate = src.rate()
  channels = src.channels()
  if channels != 1:
      error('Only mono for now')
  
#  if rate % 1000 != 0:
#      in_rate = rate + (1000 - rate % 1000)
#      front = SimpleResampler(rate, in_rate)
#  else:
#      front = Nothing()
#      in_rate = rate

  #try:
  sink = WaveSink(dbg_file, rate, 4, 2)
  #except:
  #  error('Can\'t open debug file', 3)
  
  block_size = 2048
  
  def got_frame(f):
      print nasa_time(f)

  decoder = IRIGBDecoder(rate, sink, got_frame)

  while True:
    frames = src.read(block_size)
    if frames is None:
      break
    
    samples = frames[0]
    # scaled = front.process(samples)
    decoder.process(samples)
    
if __name__ == '__main__':
  import sys
  main(sys.argv)
