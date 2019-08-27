#!/usr/bin/env python
import numpy
from ..util import JWaveSink

class WaveSink(object):
    def __init__(self, path, rate, channels, depth):
        '''Opens a WAVe file for writing.
        
        path - Pathname of file to write.
        rate - Sample rate, in hertz.
        channels - Number of channels.
        depth - Number of bytes per sample (1 = 8-bit, 2 = 16-bit, 3 = 24-bit )
        '''
        self._channels = channels
        self._depth = depth
        self._w = JWaveSink(path, rate, channels, depth)
    
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
            data = data.tobytes()
        elif self._depth == 2:
            data = (data * 0x8000).clip(-0x8000, 0x7fff).astype(numpy.int16)
            out = numpy.empty(2*framecount*self._channels, dtype=numpy.uint8)
            out[1::2] = (data >> 8) & 0xff
            out[0::2] = (data     ) & 0xff
            data = out.tobytes()
        else:
            assert(self._depth == 3)
            data = (data * 0x800000).clip(-0x800000, 0x7fffff).astype(numpy.int32)
            out = numpy.empty(3*framecount*self._channels, dtype=numpy.uint8)
            out[2::3] = (data >> 16) & 0xff
            out[1::3] = (data >>  8) & 0xff
            out[0::3] = (data      ) & 0xff
            data = out.tobytes()
        self._w.writeframes_raw(data)
    
    def close(self):
        self._w.close()

