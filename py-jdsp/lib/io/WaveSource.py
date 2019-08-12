#!/usr/bin/env python
import numpy
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
