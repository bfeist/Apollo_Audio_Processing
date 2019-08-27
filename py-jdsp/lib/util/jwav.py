'''
A WAV file reading and writing framework, replacing the standard Python
'wave' module with one that can support extra meta-data chunks.
'''
import sys
import struct
import collections

WAVEHeader = collections.namedtuple('WAVEHeader', 'id size format')
FMTHeader = collections.namedtuple('FMTHeader',
    'AudioFormat NumChannels SampleRate ByteRate BlockAlign BitsPerSample')
ChunkHeader = collections.namedtuple('ChunkHeader', 'name size')
ChunkLocator = collections.namedtuple('ChunkLocator', 'offset header')

FMTHeaderStruct = struct.Struct('<HHIIHH')

def WAVEHeader_from_src(f):
    hdr = f.read(12)
    assert(len(hdr) == 12)
    return WAVEHeader(*struct.unpack('<4sI4s', hdr))

def WAVEHeader_to_bytes(hdr):
    return struct.pack('<4sI4s', hdr.id, hdr.size, hdr.format)

def FMTHeader_from_src(f):
    return FMTHeader_from_bytes(f.read(FMTHeaderStruct.size))

def FMTHeader_from_bytes(hdr):
    assert(len(hdr) == FMTHeaderStruct.size)
    return FMTHeader(*FMTHeaderStruct.unpack(hdr))

def FMTHeader_to_bytes(hdr):
    return FMTHeaderStruct.pack(*hdr)

def ChunkHeader_from_src(f):
    return ChunkHeader_from_bytes(f.read(8))

def ChunkHeader_from_bytes(hdr):
    assert(len(hdr) == 8)
    return ChunkHeader(*struct.unpack('<4sI', hdr))

def ChunkHeader_to_bytes(hdr):
    return struct.pack('<4sI', hdr.name, hdr.size)

def ChunkLocators_from_file(f, rewind=True, limit=None):
    '''
    Quickly scan through an opened WAVE file and return Chunk locators.
    
    The opened file, f, must support the seek(), read(), and tell()
    protocol. As well, it must be positioned just past the master WAVE
    header.
    
    If limit is not None, it specifies the maximum distance within the file
    to parse. Typically, limit would come from the 'ChunkSize' element of the
    WAVE header, and it represents the asserted size of the entire file.
    '''
    if rewind:
        original_position = f.tell()
    while True:
        #
        # Read next chunk header.
        #
        if limit is not None:
            assert(f.tell() + 8 <= limit)
        hdr_b = f.read(8)
        if hdr_b == '':
            break

        #
        # Parse it.
        #
        hdr = ChunkHeader_from_bytes(hdr_b)
        locator = ChunkLocator(f.tell(), hdr)
        
        yield locator
        
        #
        # Seek to next chunk header.
        #
        if limit is not None:
            assert(f.tell() + hdr.size <= limit)
        f.seek(hdr.size, 1)
    if rewind:
        f.seek(original_position, 0)

def compute_byte_rate(channels, sample_rate, bits_per_sample):
    return channels * sample_rate * (bits_per_sample // 8)

class JWaveSource(object):
    class FormatError(Exception):
        pass

    class AlreadyReadingData(Exception):
        pass

    def __init__(self, path):
        self.path = path
        wav = self._w = open(path, 'rb')

        file_header = WAVEHeader_from_src(wav)
        self.assert_fmt(file_header.id == 'RIFF', 'Not RIFF')
        self.assert_fmt(file_header.format == 'WAVE', 'Not WAVE')

        #
        # Quickly scan through all the chunks in the file, noting their
        # identifiers and data locations.
        #
        locators_by_name = dict()
        self.locators = locators_by_name

        for locator in ChunkLocators_from_file(wav):
            self.assert_fmt(
                locators_by_name.get(locator.header.name) is None,
                'Duplicate chunks'
            )
            locators_by_name[locator.header.name] = locator

        #
        # There needs to be a fmt chunk.
        #
        fmt_locator = locators_by_name.get('fmt ')
        self.assert_fmt(fmt_locator is not None, 'No "fmt " chunk.')

        #
        # Check and break out the format header.
        #
        self.assert_fmt(fmt_locator.header.size >= FMTHeaderStruct.size,
            '"fmt " block not big enough to be correct.'
        )
        wav.seek(fmt_locator.offset, 0)
        fmt = FMTHeader_from_src(wav)
        print fmt

        #
        # Only PCM files supported at the moment.
        #
        self.assert_fmt(fmt.AudioFormat == 1, 'Not PCM file.')

        #
        # Check that items match.
        #
        computed_byte_rate = compute_byte_rate(
            fmt.NumChannels, fmt.SampleRate, fmt.BitsPerSample
        )
        self.assert_fmt(fmt.ByteRate == computed_byte_rate,
            'Mismatched byte rate')

        computed_block_align = fmt.ByteRate // fmt.SampleRate
        self.assert_fmt(fmt.BlockAlign == computed_block_align,
            'Mismatched block alignment.')

        self._framerate = fmt.SampleRate
        self._nchannels = fmt.NumChannels
        self._sampwidth = fmt.BitsPerSample // 8

        #
        # Find the data chunk.
        #
        data_locator = locators_by_name.get('data')
        self.assert_fmt(data_locator is not None, 'No "data" chunk.')

        self.data_offset = data_locator.offset

        #
        # Mark that we aren't yet in the data area.
        #
        self.in_data = False

    #
    # Python wave module compatability.
    #
    def getframerate(self):
        return self._framerate

    def getnchannels(self):
        return self._nchannels

    def getsampwidth(self):
        return self._sampwidth

    def readframes(self, frame_count):
        if not self.in_data:
            self._w.seek(self.data_offset, 0)
            self.in_data = True

        #
        # TODO!
        # XXX data portion may not be at end of file! Check limits!
        #
        return self._w.read(self._nchannels * self._sampwidth * frame_count)

    def chunks(self):
        '''
        Return a dictionary of chunks available in the file.
        
        Entries are indexed by chunk name (as a string). Entry values are
        of type ChunkLocator.
        '''
        return self.locators

    def read_chunk(self, chunk_name):
        '''
        Return the data portion of the chunk named in chunk_name.
        
        Returns the entire data portion of the identified chunk, or
        None if the chunk is not present in the file.
        
        Chunk data can only be returned if samples have yet to be read
        from the file. If samples have already been fetched (via readframes())
        then this operation raises AlreadyReadingData.
        '''
        chunk_locator = self.locators.get(chunk_name)
        if chunk_locator is None:
            return None

        if self.in_data:
            #
            # Reading chunk data will screw up the read pointer! Can't
            # do that now.
            #
            raise self.AlreadyReadingData()

        self._w.seek(chunk_locator.offset, 0)
        return self._w.read(chunk_locator.header.size)

    def assert_fmt(self, cond, msg):
        if not cond:
            raise self.FormatError(msg)
