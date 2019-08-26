#!/usr/bin/env python
from __future__ import print_function
from jdsp.io import WaveSource, WaveSink
from jdsp.blocks import ZeroCrossDetector, HighPassFilter
import numpy
import collections
import functools
from apollo import TimeBases, GMTFromIRIG, MissionTimeFromIRIG
from apollo import met_str, gmt_str
# Python 2 & 3 compatible way to get izip()
try:
    import itertools.izip as izip
except ImportError:
    izip = zip

IRIGBFrame = collections.namedtuple('IRIGBFrame',
    'seconds minutes hours days years control sbs absolute_sample')

def full_frame_time(f):
    return '%05x %02dy %03dd %02dh %02dm %02ds' % (
        f.sbs,
        f.years,
        f.days,
        f.hours,
        f.minutes,
        f.seconds
    )

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
            # We've got a deferred valley to process
            assert(len(peaks) - len(valleys) == 1)
            # Collect and store the peak value now.
            self.stored_peak_abs_s = servicable_p[-1] + self.sample_number
            self.stored_peak_value = peaks[-1]
            self.deferred_valley_index = valley_idxs[-1] - len(data)
            # Remove its peak from the collection list.
            peaks = peaks[:-1]
        elif len(unservicable_p):
            self.deferred_peak_index = unservicable_p[0] - len(data)

        amplitudes = peaks - valleys

        if len(amplitudes):
            self.receive_pulses(
                servicable_p + self.sample_number - self.quarter_phase_samples,
                amplitudes
            )

        self.sample_number += len(data)

    def receive_pulses(self, start_sample_no, amplitudes):
        for n, amplitude in izip(start_sample_no, amplitudes):
            split_point = self.last_n_amplitudes.mean()
            self.last_n_amplitudes[self.amplitudes_i] = amplitude
            self.amplitudes_i = (self.amplitudes_i + 1) % 100
            self.framer.receive_bit(n, amplitude > split_point)

def prepend(array, value, dtype):
    n = numpy.empty(len(array) + 1, dtype=dtype)
    n[0] = value
    n[1:] = array
    return n

def frame_dump_audacity(b, rate, f):
    mission = met_str(MissionTimeFromIRIG(b, f))
    frame = gmt_str(GMTFromIRIG(b, f))
    tm = '%f' % (float(f.absolute_sample) / rate)
    print(tm + '\t' + tm + '\t' + mission, frame)

def frame_dump_plain(b, rate, f):
    mission = met_str(MissionTimeFromIRIG(b, f))
    frame = gmt_str(GMTFromIRIG(b, f))
    print(mission, frame, '%09d' % f.absolute_sample)

def frame_dump_raw(b, rate, f):
    print(full_frame_time(f))

def start_dump_adobe(b, rate):
    print('Name', 'Start', 'Duration', 'Time Format', 'Type', 'Description',
        sep='\t')

def frame_dump_adobe(b, rate, f):
    met = met_str(MissionTimeFromIRIG(b, f))
    gmt = gmt_str(GMTFromIRIG(b, f))
    sec = float(f.absolute_sample) / rate
    h = int(sec / 3600.0)
    m = int(sec / 60.0) % 60
    s = sec % 60
    st = '%d:%d:%09.6f' % (h, m, s)
    print(met, st, '0:0:0', 'decimal', 'Cue', gmt, sep='\t')

def main(args):
    import getopt

    def usage(prog):
      print('usage:', prog, '[-i] [-a|-p|-l|-r] [-b <base>] <wav-file>',
          file=sys.stderr)
      print('-i  Invert audio before processing.', file=sys.stderr)
      print('-b  Translate time for specific mission basis.', file=sys.stderr)
      print('    (Available bases: {}).'.format(' '.join(time_bases.keys())),
            file=sys.stderr)
      print('  Options for output', file=sys.stderr)
      print('-l  Write Audacity-compatible labels on output.', file=sys.stderr)
      print('-a  Write Adobe Audition markers on output.', file=sys.stderr)
      print('-p  Write plain labels on output.', file=sys.stderr)
      print('-r  Write raw labels on output.', file=sys.stderr)

      sys.exit(1)

    def error(msg, code):
        print(msg, file=sys.stderr)
        sys.exit(code)

    def fatal(msg):
        raise Exception(msg)

    prog = args[0]
    args = args[1:]
    invert = False
    styles = set()

    basis_name = 'a11'

    opts, args = getopt.getopt(args, 'arpilhb:')
    for opt, val in opts:
        if opt == '-i':
            invert = True
        elif opt == '-l':
            styles.add('audacity')
        elif opt == '-a':
            styles.add('adobe')
        elif opt == '-r':
            styles.add('raw')
        elif opt == '-p':
            styles.add('plain')
        elif opt == '-b':
            basis_name = val.lower()
        elif opt == '-h':
            usage(prog)

    if len(args) < 1:
        usage(prog)

    if len(styles) > 1:
        error('More than one label style specified. Choose only one.')
    elif len(styles) == 0:
        style = 'audacity'
    else:
        style = styles.pop()

    mission_basis = TimeBases.get(basis_name, None)
    if mission_basis is None:
        error('Unknown mission name.', 2)

    in_file = args[0]

    try:
        src = WaveSource(in_file)
    except:
        error('Can\'t open input file', 2)

    rate = src.rate()
    channels = src.channels()
    if channels != 1:
          error('Only mono for now')

    block_size = int(rate)

    five_ms_samples = int(rate * 0.005)
    if (five_ms_samples % 2) == 0:
        five_ms_samples += 1
    hp = HighPassFilter(rate, five_ms_samples, 400.0)

    if style == 'audacity':
        dump = frame_dump_audacity
    elif style == 'adobe':
        start_dump_adobe(mission_basis, rate)
        dump = frame_dump_adobe
    elif style == 'raw':
        dump = frame_dump_raw
    elif style == 'plain':
        dump = frame_dump_plain
    else:
        error('Internal error while selecting dump format.')

    callback = functools.partial(dump, mission_basis, rate)

    decoder = IRIGBDecoder(rate, callback)

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
