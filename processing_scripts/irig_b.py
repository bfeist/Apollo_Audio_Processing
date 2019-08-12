#!/usr/bin/env python
from __future__ import print_function
from jdsp.io import WaveSource, WaveSink
from jdsp.blocks import ZeroCrossDetector, HighPassFilter
import numpy
import collections
import itertools

IRIGBFrame = collections.namedtuple('IRIGBFrame',
    'seconds minutes hours days years control sbs absolute_sample')

def frame_time(f):
    return '%05x %02dy %03dd %02dh %02dm %02ds' % (
        f.sbs,
        f.years,
        f.days,
        f.hours,
        f.minutes,
        f.seconds
    )

#
# Apollo 11 range zero time is 13:32:00, July 16, 1969
# That is day #197 (one-based)
#
apollo_11_T_0 = (((197 * 24) + 13) * 60 + 32) * 60

def nasa_time(f):
    year_seconds = (((((f.years * 365) + f.days) * 24 + f.hours) * 60 +
        f.minutes) * 60) + f.seconds
    mission_seconds = year_seconds - apollo_11_T_0
    hours = mission_seconds / 3600
    minutes = (mission_seconds / 60) % 60
    seconds = mission_seconds % 60
    return '%03d:%02d:%02d' % (hours, minutes, seconds)

def gmt_from_nasa(h, m, s):
    mission_seconds = ((h * 60) + m) * 60 + s
    year_seconds = mission_seconds + apollo_11_T_0
    s = year_seconds % 60
    m = (year_seconds / 60) % 60
    h = (year_seconds / 3600) % 24
    d = (year_seconds / 86400) % 365
    return '%02dd %02dh %02dm %02ds' % (d, h, m, s)

class IRIGBDeframer(object):
    def __init__(self, receiver):
        self.frame_pos = 0
        self.pulse_pos = 0
        self.big_count = 0
        self.word = 0
        self.receiver = receiver
        self.state_handle = self.receive_bit_in_idle
        self.bit_times = numpy.empty(10, dtype='int64')
        self.bit_times_i = 0
    
    def receive_bit(self, abs_samp, bit):
        self.bit_times[self.bit_times_i] = abs_samp
        self.bit_times_i = (self.bit_times_i + 1) % 10
        self.word <<= 1
        self.word &= 0xfffff
        if bit:
            self.word |= 1
        self.state_handle(bit)
        
    def receive_bit_in_idle(self, bit):
        if self.word == 0xff3fc:
            # print 'DOUBLE SYNC'
            self.frame_pos = 1
            self.pulse_pos = 0
            self.big_count = 0
            self.ten_word = 0x200
            self.seconds = 0
            self.minutes = 0
            self.hours = 0
            self.days_low = 0
            self.days_high = 0
            self.years = 0
            self.control_low = 0
            self.control_high = 0
            self.sbs_low = 0
            self.sbs_high = 0
            self.frame_abs_samp = self.bit_times[self.bit_times_i]
            self.state_handle = self.receive_bit_in_sync

    def receive_bit_in_sync(self, bit):
        if bit:
            self.big_count += 1
        self.pulse_pos += 1
        if self.pulse_pos == 10:
            if self.big_count >= 8:
                # print "SYNC"
                bit = 1
            elif self.big_count >= 5:
                # print "1",
                bit = 1
            else:
                # print "0",
                bit = 0
            self.ten_word >>= 1
            if bit:
                self.ten_word |= 0x200
            self.pulse_pos = 0
            self.big_count = 0
            self.frame_pos += 1
            if self.frame_pos == 10:
                seconds_units = (self.ten_word >> 1) & 0xf
                seconds_tens = (self.ten_word >> 6) & 0x7
                self.seconds = seconds_units + seconds_tens * 10
            elif self.frame_pos == 20:
                minutes_units = self.ten_word & 0xf
                minutes_tens = (self.ten_word >> 5) & 0x7
                self.minutes = minutes_units + minutes_tens * 10
            elif self.frame_pos == 30:
                hours_units = self.ten_word & 0xf
                hours_tens = (self.ten_word >> 5) & 0x3
                self.hours = hours_units + hours_tens * 10
            elif self.frame_pos == 40:
                days_low_units = self.ten_word & 0xf
                days_low_tens = (self.ten_word >> 5) & 0xf
                self.days_low = days_low_units + days_low_tens * 10
            elif self.frame_pos == 50:
                days_high_units = self.ten_word & 0x3
                self.days_high = days_high_units
            elif self.frame_pos == 60:
                years_units = self.ten_word & 0xf
                years_tens = (self.ten_word >> 5) & 0xf
                self.years = years_units + years_tens * 10
            elif self.frame_pos == 70:
                self.control_low = self.ten_word & 0x1ff
            elif self.frame_pos == 80:
                self.control_high = self.ten_word & 0x1ff
            elif self.frame_pos == 90:
                self.sbs_low = self.ten_word & 0x1ff
            if self.frame_pos == 99:
                self.sbs_high = (self.ten_word >> 1) & 0xff
                self.dump_frame()
                # print "got 99 bits"
                self.state_handle = self.receive_bit_in_idle

    def dump_frame(self):
        frame = IRIGBFrame(
            self.seconds,
            self.minutes,
            self.hours,
            self.days_low + self.days_high * 100,
            self.years,
            self.control_low | (self.control_high << 9),
            self.sbs_low | (self.sbs_high << 9),
            self.frame_abs_samp
        )
        self.receiver(frame)

class IRIGBDecoder(object):
    '''An IRIG-B decoder.'''

    def __init__(self, rate, receiver):
        '''Instantiate an IRIG-B decoder for a given sample rate.

        rate - Sampling rate, in hertz.
        receiver - Callable to receive decoded frames.'''
        #assert((rate % 1000) == 0)
        self.zc = ZeroCrossDetector(rate, 1000.0)
        self.framer = IRIGBDeframer(receiver)
        self.quarter_phase_samples = int((rate / 1000.0) / 4.0)
        self.half_phase_samples = int((rate / 1000.0) / 2.0)
        self.last_n_amplitudes = numpy.zeros(100, dtype='float')
        self.last_n_amplitudes[range(50)] = 1.0
        self.amplitudes_i = 0
        self.deferred_peak_index = None
        self.deferred_valley_index = None
        self.sample_number = 0
    
    def set_sample_number(self, n):
        '''Set the starting sample number, useful if input is delayed.'''
        self.sample_number = n
    
    def process(self, data):
        '''Decode the given data, returning frames found, if any.'''
        #
        # Detect plausible zero crossings in the data.
        #
        cross_points = self.zc.process(data)
        
        #
        # Calculate the peak waveform points given the zero crossing
        # indexes.
        #
        peak_idxs = cross_points + self.quarter_phase_samples
        
        #if self.sample_number == 3082240:
        #    print "at", self.sample_number
        #    print "zeros", cross_points + self.sample_number
        
        #
        # If there's a deferred peak to collect, incorporate
        # it.
        #
        if self.deferred_peak_index is not None:
            assert(self.deferred_valley_index is None)
            if self.deferred_peak_index < len(data):
                if len(peak_idxs):
                    assert(self.deferred_peak_index < peak_idxs[0])
                peak_idxs = prepend(peak_idxs, self.deferred_peak_index,'int32')
                self.deferred_peak_index = None
            else:
                self.deferred_peak_index -= len(data)
        elif self.deferred_valley_index is not None:
            #
            # There's a deferred valley to collect.
            #
            assert(self.deferred_peak_index is None)
            #print self.sample_number, self.deferred_valley_index, "deferred valley"
            if self.deferred_valley_index < len(data):
                amplitude = self.stored_peak_value - \
                    data[self.deferred_valley_index]
                self.receive_pulses(
                    (self.stored_peak_abs_s,),
                    (amplitude,)
                )
                self.stored_peak_abs_s = None
                self.stored_peak_value = None
                self.deferred_valley_index = None
            else:
                self.deferred_valley_index -= len(data)
        
        valley_idxs = peak_idxs + self.half_phase_samples
        
        servicable_p = peak_idxs[peak_idxs < len(data)]
        servicable_v = valley_idxs[valley_idxs < len(data)]
        peaks = data[servicable_p]
        valleys = data[servicable_v]
        unservicable_p = peak_idxs[peak_idxs >= len(data)]
        
        if len(peaks) > len(valleys):
            # print "deferring valley", self.sample_number, valley_idxs[-1]
            # We've got a deferred valley to process
            assert(len(peaks) - len(valleys) == 1)
            # Collect and store the peak value now.
            self.stored_peak_abs_s = servicable_p[-1] + self.sample_number
            self.stored_peak_value = peaks[-1]
            self.deferred_valley_index = valley_idxs[-1] - len(data)
            # Remove its peak from the collection list.
            peaks = peaks[:-1]
        elif len(unservicable_p):
            # print "deferring peak", self.sample_number, unservicable_p[0]
            self.deferred_peak_index = unservicable_p[0] - len(data)
        
        amplitudes = peaks - valleys

        if len(amplitudes):
            self.receive_pulses(
                servicable_p + self.sample_number - self.quarter_phase_samples,
                amplitudes
            )
        
        self.sample_number += len(data)
    
    def receive_pulses(self, start_sample_no, amplitudes):
        for n, amplitude in itertools.izip(start_sample_no, amplitudes):
            split_point = self.last_n_amplitudes.mean()
            self.last_n_amplitudes[self.amplitudes_i] = amplitude
            self.amplitudes_i = (self.amplitudes_i + 1) % 100
            #if n >= 3084225 and n <= 3085471:
            #    print n, split_point, amplitude
            self.framer.receive_bit(n, amplitude > split_point)

def prepend(array, value, dtype):
    n = numpy.empty(len(array) + 1, dtype=dtype)
    n[0] = value
    n[1:] = array
    return n

def main(args):
  import getopt

  def usage(prog):
    print('usage:', prog, '[-i] [-l] <wav-file>', file=sys.stderr)
    print('-i  Invert audio before processing.', file=sys.stderr)
    print('-l  Write Audacity-compatible labels on output.', file=sys.stderr)
    sys.exit(1)

  def error(msg, code):
    print(msg, file=sys.stderr)
    sys.exit(code)

  def fatal(msg):
    raise Exception(msg)

  prog = args[0]
  args = args[1:]
  invert = False
  labels = False

  opts, args = getopt.getopt(args, 'il')
  for opt, val in opts:
      if opt == '-i':
          invert = True
      elif opt == '-l':
          labels = True
      
  if len(args) < 1:
    usage(prog)

  in_file = args[0]

  try:
    src = WaveSource(in_file)
  except:
    error('Can\'t open input file', 2)

  rate = src.rate()
  channels = src.channels()
  if channels != 1:
      error('Only mono for now')
    
  block_size = 44100
  
  def got_frame(f):
      if labels:
          tm = '%f' % (float(f.absolute_sample) / rate)
          print(tm + '\t' + tm + '\t' + nasa_time(f), frame_time(f))
      else:
          print(nasa_time(f), frame_time(f), '%09d' % f.absolute_sample)

  five_ms_samples = int(rate * 0.005)
  if (five_ms_samples % 2) == 0:
      five_ms_samples += 1
  hp = HighPassFilter(rate, five_ms_samples, 400.0)
  decoder = IRIGBDecoder(rate, got_frame)
  decoder.set_sample_number(hp.delay() * -1)
  
  while True:
    frames = src.read(block_size)
    if frames is None:
      break
    
    samples = frames[0]
    if invert:
        samples = samples * -1.0
    filtered = hp.process(samples)
    decoder.process(filtered)
    
if __name__ == '__main__':
  import sys
  main(sys.argv)
