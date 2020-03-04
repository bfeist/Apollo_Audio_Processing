#!/usr/bin/env python
#
# Copyright 2019 Jeremy Cooper.
#
# This file is unpublished proprietary source code. It is licensed
# for use by members of the the Apollo Audio project ("ApolloAudio"),
# who are determined at the sole discretion of Ben Feist, for use on archival
# audio produced by NASA's Apollo programs ("Apollo Material"), determined
# at the sole discretion of Jeremy Cooper.
#
# Any use outside of ApolloAudio, and/or on material other than Apollo
# Material is prohibited.
#
from __future__ import print_function
from jdsp.io import WaveSource, WaveSink
from jdsp.blocks import ZeroCrossDetector, HighPassFilter
from numpy import rint, zeros, empty
import collections
import functools
import datetime
from apollo import TimeBases, DatetimeGMTFromIRIG, ETFromDatetimeGMT
from apollo import MissionTimeBasis
from apollo import met_str, gmt_str
# Python 2 & 3 compatible way to get izip()
try:
    import itertools.izip as izip
except ImportError:
    izip = zip

IRIGBFrame = collections.namedtuple('IRIGBFrame',
    'seconds minutes hours days years control sbs absolute_sample ok_sbs_tm')

#
# For very accurate timing information across long time periods (weeks),
# we represent an absolute sample position as an integer part and a separate
# fractional part. Combining these into a single floating point value would
# loose precision in these scales.
#
# NOTE: The fractional part may be negative!
#
AbsoluteSample = collections.namedtuple('AbsoluteSample', 'i f')

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
        self.bit_zc_times = [ AbsoluteSample(0, 0) for i in range(10) ]
        self.bit_zc_times_i = 0

    def receive_bit(self, abs_zc_time, bit):
        '''
        Receive an incoming bit.
        
        bit -- The bit value.
        abs_zc_time -- The absolute sample time of the point where the
            bit actually started in the sample stream. (This should be
            an AbsoluteSample type).
        '''
        self.bit_zc_times[self.bit_zc_times_i] = abs_zc_time
        self.bit_zc_times_i = (self.bit_zc_times_i + 1) % 10
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
            self.frame_abs_samp = self.bit_zc_times[self.bit_zc_times_i]
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
        #
        # There's no parity or other error checking in IRIG-B. But there
        # is some redundancy we can use to check for errors. The SBS field
        # should theoretically match the hours, minutes and seconds fields.
        #
        sbs = self.sbs_low | (self.sbs_high << 9)
        sbs_tm_ok = sbs == (self.hours * 3600 + self.minutes * 60 + self.seconds)

        frame = IRIGBFrame(
            self.seconds,
            self.minutes,
            self.hours,
            self.days_low + self.days_high * 100,
            self.years,
            self.control_low | (self.control_high << 9),
            sbs,
            self.frame_abs_samp,
            sbs_tm_ok
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
        self.quarter_phase_samples = (rate / 1000.0) / 4.0
        self.half_phase_samples = (rate / 1000.0) / 2.0
        if self.quarter_phase_samples < 1.0:
            raise Exception('Sample rate too low for signal.')
        self.last_n_amplitudes = zeros(100, dtype='float')
        self.last_n_amplitudes[range(50)] = 1.0
        self.amplitudes_i = 0
        self.deferred_peak_index = None
        self.deferred_peak_index_f = None
        self.deferred_peak_zc_time = None
        self.deferred_valley_index = None
        self.sample_number = 0

    def set_sample_number(self, n):
        '''Set the starting sample number, useful if input is delayed.'''
        self.sample_number = n

    def process(self, data):
        '''Decode the given data, returning frames found, if any.'''
        #
        # Detect plausible zero crossings in this block of samples.
        #
        # cross_point is the index of the sample just _after_ the
        # zero crossing point detected. fraction is the distance from the
        # crossing point to that sample, which will always be in the
        # range [0, 1).
        #
        cross_points, fractions = self.zc.process(data)

        #
        # Compute their absolute sample times, for future use.
        #
        cross_times = [
            AbsoluteSample(i_part, f_part)
            for i_part, f_part in
                izip(cross_points + self.sample_number, -fractions)
        ]

        #
        # Calculate the peak waveform points given the zero crossing
        # indexes.
        #
        peak_idxs = cross_points - fractions + self.quarter_phase_samples

        #
        # Round each of these points to the nearest integer.
        #
        ipeak_idxs = rint(peak_idxs).astype('int32')

        #
        # Sometimes a peak is calculated to occur just beyond a processing
        # block. When this happens the peak is "deferred" into the next
        # block. See if that condition has happened in the previous block, and
        # if so, see if it can be collected in this block.
        #
        if self.deferred_peak_index is not None:
            #
            # There is a deferred peak to collect. Most likely it is
            # collectable now.
            #
            # First off, there should never be a both a deferred valley and
            # a deferred peak.
            #
            assert(self.deferred_valley_index is None)

            #
            # Is the deferred peak inside the current block?
            #
            if self.deferred_peak_index < len(data):
                #
                # It's inside this block. Are there any regular (non-deferred)
                # peaks in this block?
                #
                if len(ipeak_idxs):
                    #
                    # There are other peaks. The deferred one must come before
                    # any other ones.
                    #
                    assert(self.deferred_peak_index < ipeak_idxs[0])

                #
                # Incorporate the deferred peak into the peaks to collect
                # in this block.
                #
                ipeak_idxs = prepend(ipeak_idxs, self.deferred_peak_index,
                    'int32')
                peak_idxs = prepend(peak_idxs, self.deferred_peak_index_f,
                    'float')
                cross_times.insert(0, self.stored_zc_time)

                #
                # Mark that the deferment has been taken.
                #
                self.deferred_peak_index = None
                self.deferred_peak_index_f = None
                self.stored_zc_time = None
            else:
                #
                # The deferred peak is somehow beyond even this block! This
                # can happen if the input blocks are small. Anyways, update
                # the deferred peak point to account for the data that is
                # in this block.
                #
                self.deferred_peak_index -= len(data)
                self.deferred_peak_index_f -= len(data)
        elif self.deferred_valley_index is not None:
            #
            # There's a deferred valley to collect. Most likely it is
            # collectable now.
            #
            # But first off, there should never be a both a deferred valley and
            # a deferred peak.
            #
            assert(self.deferred_peak_index is None)

            #
            # Is the deferred valley inside the current block?
            #
            if self.deferred_valley_index < len(data):
                #
                # The deferred valley is inside this block.
                #
                # With the deferred valley we can finally compute the
                # amplitude of the wave portion from the peak to the valley,
                # and as such, we are ready to report the peak-to-peak
                # measurement up to the framing and decoding engine.
                #

                #
                # Compute the peak-to-peak amplitude.
                #
                amplitude = self.stored_peak_value - \
                    data[self.deferred_valley_index]

                #
                # Notify the decoder of this single wave pulse.
                #
                self.receive_pulses(
                    (self.stored_zc_time,),
                    (amplitude,)
                )

                #
                # Mark the deferred valley as serviced.
                #
                self.stored_zc_time = None
                self.stored_peak_value = None
                self.deferred_valley_index = None
            else:
                #
                # Ths deferred valley is still outside this block. Update
                # the valley point to account for this data in this block.
                #
                self.deferred_valley_index -= len(data)

        #
        # Compute the locations of the expect signal valleys.
        #
        valley_idxs = peak_idxs + self.half_phase_samples

        #
        # Round each valley index to the nearest integer. The fractional
        # part needn't be kept.
        #
        ivalley_idxs = rint(valley_idxs).astype('int32')

        #
        # We can't fetch samples that have already been thrown away. Make
        # sure we haven't made an algorithmic error.
        #
        assert((ipeak_idxs >= 0).all())
        assert((ivalley_idxs >= 0).all())

        #
        # Find the servicable peak and valley samples in the current
        # data buffer.
        #
        servicable_indexes = ipeak_idxs < len(data)
        servicable_p = ipeak_idxs[servicable_indexes]
        servicable_v = ivalley_idxs[ivalley_idxs < len(data)]

        #
        # Fetch those peak and valley values.
        #
        peaks = data[servicable_p]
        valleys = data[servicable_v]

        #
        # Find the unservicable peaks, if any. These are peaks that
        # will need to be deferred until the next block.
        #
        unservicable_indexes = ipeak_idxs >= len(data)
        unservicable_p = ipeak_idxs[unservicable_indexes]
        # There should be no more than one, ever.
        assert(len(unservicable_p) <= 1)

        if len(peaks) > len(valleys):
            # We've got a deferred valley to process
            assert(len(peaks) - len(valleys) == 1)
            # Collect and store the peak value now.
            self.stored_zc_time = cross_times[-1]
            self.stored_peak_value = peaks[-1]
            self.deferred_valley_index = ivalley_idxs[-1] - len(data)
            # Remove its peak from the collection list.
            peaks = peaks[:-1]
            cross_times = cross_times[:-1]
        elif len(unservicable_p):
            self.stored_zc_time = cross_times[-1]
            self.deferred_peak_index = unservicable_p[0] - len(data)
            self.deferred_peak_index_f = peak_idxs[unservicable_indexes][0] - \
                len(data)

        amplitudes = peaks - valleys

        if len(amplitudes):
            #
            # We have a full set of bit waveforms ready now. Send them, and
            # their starting positions, up to the decoder.
            #
            self.receive_pulses(
                cross_times,
                amplitudes
            )

        self.sample_number += len(data)

    def receive_pulses(self, start_sample_times, amplitudes):
        for t, amplitude in izip(start_sample_times, amplitudes):
            split_point = self.last_n_amplitudes.mean()
            self.last_n_amplitudes[self.amplitudes_i] = amplitude
            self.amplitudes_i = (self.amplitudes_i + 1) % 100
            self.framer.receive_bit(t, amplitude > split_point)

def prepend(array, value, dtype):
    n = empty(len(array) + 1, dtype=dtype)
    n[0] = value
    n[1:] = array
    return n

def frame_filter_sbs_match(b, rate, f):
    return f.ok_sbs_tm

def frame_filter_year_zero(b, rate, f):
    return f.years == 0

def frame_dump_audacity_with_met(b, rate, f):
    dt = DatetimeGMTFromIRIG(b, f)
    mission = met_str(ETFromDatetimeGMT(b, dt))
    frame = gmt_str(dt)
    t = float(f.absolute_sample.i) / rate
    t += f.absolute_sample.f / rate
    tm = '%f' % t
    print(tm, tm, mission, sep='\t', end=' ')
    print(frame)

def frame_dump_audacity(b, rate, f):
    dt = DatetimeGMTFromIRIG(b, f)
    frame = gmt_str(dt)
    t = float(f.absolute_sample.i) / rate
    t += f.absolute_sample.f / rate
    tm = '%f' % t
    print(tm, tm, frame, sep='\t')

def frame_dump_plain(b, rate, f):
    dt = DatetimeGMTFromIRIG(b, f)
    mission = met_str(ETFromDatetimeGMT(b, dt))
    frame = gmt_str(dt)
    print(mission, frame, '%09d' % f.absolute_sample.i)

def frame_dump_raw(b, rate, f):
    print(full_frame_time(f))

def start_dump_adobe(b, rate):
    print('Name', 'Start', 'Duration', 'Time Format', 'Type', 'Description',
        sep='\t')

def frame_dump_adobe(b, rate, f):
    dt = DatetimeGMTFromIRIG(b, f)
    met = met_str(ETFromDatetimeGMT(b, dt))
    gmt = gmt_str(dt)
    sec = float(f.absolute_sample.i) / rate
    sec += float(f.absolute_sample.f) / rate
    h = int(sec / 3600.0)
    m = int(sec / 60.0) % 60
    s = sec % 60
    st = '%d:%d:%09.6f' % (h, m, s)
    print(met, st, '0:0:0', 'decimal', 'Cue', gmt, sep='\t')

def main(args):
    import getopt

    def usage(prog):
      msg = \
          'usage: {prog} [-i] [-s <skipsec>] [-F] [-a|-p|-l|-r] [-f <filter>]'\
          '[-b <base>|-y <year>] ' \
          '<wav-file>\n' \
          '  Options for input\n' \
          '-s  Skip <skipsec> seconds of audio before processing.\n' \
          '    Can also be negative, in which case decoding will start\n' \
          '    -<skipsec> seconds before the end of the file.\n' \
          '-i  Invert audio before processing.\n' \
          '-F  Apply 400 Hz high-pass filter to audio before processing.\n' \
          '    (Useful for some signals.)\n' \
          '  Options for output\n' \
          '-b  Translate time for specific mission basis.\n' \
          '    (Available bases: {bases}).\n' \
          '-y  Translate time for specified year.\n' \
          '-l  Write Audacity-compatible labels on output.\n' \
          '-a  Write Adobe Audition markers on output.\n' \
          '-p  Write plain labels on output.\n' \
          '-r  Write raw labels on output.\n' \
          '  Frame filtering\n' \
          '-f  Filter frames according to pattern in <filter>\n' \
          '    Filter is any combination of the characters:\n' \
          '      y - Filter out frames with non-zero year fields\n' \
          '      b - Filter out frames where SBS != H:M:S fields.\n' \
          '          (SBS = Straight Binary Seconds)\n' \
          '    (Default: \'by\')\n' \
      .format(prog=prog, bases=' '.join(TimeBases.keys()))
      print(msg, file=sys.stderr)
      sys.exit(1)

    def error(msg, code):
        print(msg, file=sys.stderr)
        sys.exit(code)

    def fatal(msg):
        raise Exception(msg)

    prog = args[0]
    args = args[1:]
    invert = False
    do_skip = False
    hp_filter = False
    frame_filter_expr = None
    styles = set()

    apollo_basis_requested = False
    year_basis_requested = False
    basis_name = 'a11'

    opts, args = getopt.getopt(args, 'as:Frpilhb:f:y:')
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
            apollo_basis_requested = True
            basis_name = val.lower()
        elif opt == '-f':
            frame_filter_expr = val
        elif opt == '-y':
            year_basis_requested = True
            year_base = int(val)
        elif opt == '-F':
            hp_filter = True
        elif opt == '-s':
            do_skip = True
            skip_secs = float(val)
        elif opt == '-h':
            usage(prog)

    if len(args) < 1:
        usage(prog)

    if len(styles) > 1:
        error('More than one label style specified. Choose only one.', 2)
    elif len(styles) == 0:
        style = 'audacity'
    else:
        style = styles.pop()

    if apollo_basis_requested and year_basis_requested:
        error('Only one of -b or -y may be specified, not both.', 2)

    if year_basis_requested:
        mission_basis = MissionTimeBasis(
            all_balls=0,
            year=year_base
        )
    else:
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
    total_samples = src._w.getnframes()
    total_secs = total_samples / rate

    if channels != 1:
          error('Only mono for now')

    if do_skip:
        if skip_secs < 0.0:
            skip_secs = total_secs + skip_secs

        skip = skip_secs * rate

        if skip >= total_samples:
            error('Skip setting is too big. Total size is {:f} seconds'.format(
                total_secs), 1)
    else:
        skip = 0

    assert(skip < total_samples)

    #
    # Set things up to read one nominal second of audio per processing
    # cycle.
    #
    block_size = int(rate)

    if hp_filter:
        five_ms_samples = int(rate * 0.005)
        if (five_ms_samples % 2) == 0:
            five_ms_samples += 1
        hp = HighPassFilter(rate, five_ms_samples, 400.0)

    if style == 'audacity':
        if year_basis_requested:
            # Year-wise basis requested, no mission in effect.
            dump = frame_dump_audacity
        else:
            # We're likely processing a mission, add mission elapsed time.
            dump = frame_dump_audacity_with_met
    elif style == 'adobe':
        start_dump_adobe(mission_basis, rate)
        dump = frame_dump_adobe
    elif style == 'raw':
        dump = frame_dump_raw
    elif style == 'plain':
        dump = frame_dump_plain
    else:
        error('Internal error while selecting dump format.')

    frame_filter_func = None
    if frame_filter_expr is not None:
        for c in frame_filter_expr:
            if c == 'y':
                next_filter = frame_filter_year_zero
            elif c == 'b':
                next_filter = frame_filter_sbs_match
            else:
                error('Unknown frame filter type \'{}\'.'.format(c))

            if frame_filter_func is None:
                frame_filter_func = next_filter
            else:
                frame_filter_func = \
                     lambda  a, b, c: next_filter(a, b, c) and \
                                      frame_filter_func(a, b, c)

    if frame_filter_func is not None:
        def callback(frame):
            if frame_filter_func(mission_basis, rate, frame):
                dump(mission_basis, rate, frame)
    else:
        callback = functools.partial(dump, mission_basis, rate)

    decoder = IRIGBDecoder(rate, callback)

    if hp_filter:
        delay = hp.delay()
        decoder_process = lambda samples: decoder.process(hp.process(samples))
    else:
        delay = 0
        decoder_process = decoder.process

    decoder.set_sample_number(skip - delay)

    src._w.setpos(skip)

    while True:
        frames = src.read(block_size)
        if frames is None:
            break

        samples = frames[0]
        if invert:
            samples = samples * -1.0
        decoder_process(samples)

if __name__ == '__main__':
    import sys
    main(sys.argv)
