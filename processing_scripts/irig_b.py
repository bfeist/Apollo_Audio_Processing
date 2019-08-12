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
        outphase = numpy.empty(left, dtype='float')
        while left > 0:
            phasor = numpy.arange(self.phase, twopi, self.incr)
            if len(phasor) > left:
                phasor = phasor[0:left]
            part = data[i:i+len(phasor)]
            outphase[i:i+len(phasor)] = phasor
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

class IRIGBDecoder(object):
    '''An IRIG-B decoder.'''

    def __init__(self, rate, dbg, receiver):
        '''Instantiate an IRIG-B decoder for a given sample rate.

        rate - Sampling rate, in hertz.
        receiver - Callable to receive decoded frames.'''
        #assert((rate % 1000) == 0)

        self._pll = PLL(rate, 1000.0, 1, 0.1)
        self._dbg = dbg
        self._last_crest = False
        self._last_trough = False
        self._have_delayed_crest = False
        self._last_crest_i = 0
        self._sample_number = 0
        self._frame_state = 'idle'
        self._frame_pos = 0
        self._pulse_pos = 0
        self._big_count = 0
        self._sync_word = 0
        self._receiver = receiver
        
    def process(self, data):
        '''Decode the given data, returning frames found, if any.'''
        # Run the PLL against the input signal, returning the oscillator phase
        phase = self._pll.process(data)
        # Find the peak and crest points of the oscillator
        post_crest = numpy.empty(len(data)+1, dtype='bool')
        post_trough = numpy.empty(len(data)+1, dtype='bool')
        post_crest[0] = self._last_crest
        post_trough[0] = self._last_trough
        post_crest[1:] = phase >= (pi / 2.0)
        post_trough[1:] = phase >= (pi * 1.5)
        self._last_crest = post_crest[-1]
        self._last_trough = post_trough[-1]

        trough_points = numpy.where((~post_trough[:-1]) & post_trough[1:])[0]
        crest_points = numpy.where((~post_crest[:-1]) & post_crest[1:])[0]

        if self._have_delayed_crest:
            crests = numpy.empty(len(crest_points) + 1, dtype='float')
            crests[0] = self._delayed_crest
            crests[1:] = data[crest_points]
            self._have_delayed_crest = False
        else:
            crests = data[crest_points]
        
        if len(crests) > len(trough_points):
            self._delayed_crest = crests[-1]
            self._delayed_crest_i = crest_points[-1] + self._sample_number
            self._have_delayed_crest = True
            crests = crests[:-1]
            assert(len(crests) == len(trough_points))
        
        troughs = data[trough_points]
        
        if len(crests):
            pulses = crests - troughs
            # print pulses
            self.receive_pulses(pulses)

        self._sample_number += len(data)
        # self._dbg.write(dbg_out)
    
    def sample_now(self, sample):
        pass
    
    def receive_pulses(self, amplitudes):
        for amplitude in amplitudes:
            big = abs(amplitude) > 0.5
            if self._frame_state == 'idle':
                self._sync_word <<= 1
                self._sync_word &= 0xfffff
                if big:
                    self._sync_word |= 1
                if self._sync_word == 0xff3fc:
                    print 'SYNC'
                    self._frame_state = 'sync'
                    self._frame_pos = 1
                    self._pulse_pos = 0
                    self._big_count = 0
            else:
                if big:
                    self._big_count += 1
                self._pulse_pos += 1
                if self._pulse_pos == 10:
                    if self._big_count >= 7:
                        print "SYNC"
                    elif self._big_count >= 4:
                        print "1",
                    elif self._big_count >= 2:
                        print "0",
                    else:
                        print "?",
                    self._pulse_pos = 0
                    self._big_count = 0
                    self._frame_pos += 1
                    if self._frame_pos == 99:
                        print "got 99 bits"
                        self._frame_state = 'idle'
                        self._sync_word = 0

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
  sink = WaveSink(dbg_file, rate, 3, 2)
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
