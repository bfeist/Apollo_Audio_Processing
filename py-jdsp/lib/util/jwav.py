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
'''
A WAV file reading and writing framework, replacing the standard Python
'wave' module with one that can support extra meta-data chunks.
'''
import struct
import collections

WAVEHeader = collections.namedtuple('WAVEHeader', 'id size format')
FMTChunk = collections.namedtuple('FMTChunk',
    'AudioFormat NumChannels SampleRate ByteRate BlockAlign BitsPerSample')
ChunkHeader = collections.namedtuple('ChunkHeader', 'name size')
ChunkLocator = collections.namedtuple('ChunkLocator', 'offset header')

FMTChunkStruct = struct.Struct('<HHIIHH')
Int = struct.Struct('<I')

def WAVEHeader_from_src(f):
    hdr = f.read(12)
    assert(len(hdr) == 12)
    return WAVEHeader(*struct.unpack('<4sI4s', hdr))

def WAVEHeader_to_bytes(hdr):
    return struct.pack('<4sI4s', hdr.id, hdr.size, hdr.format)

def WAVEHeader_size():
    return 12

def FMTChunk_from_src(f):
    return FMTChunk_from_bytes(f.read(FMTChunkStruct.size))

def FMTChunk_from_bytes(hdr):
    assert(len(hdr) == FMTChunkStruct.size)
    return FMTChunk(*FMTChunkStruct.unpack(hdr))

def FMTChunk_to_bytes(hdr):
    return FMTChunkStruct.pack(*hdr)

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
        if hdr_b == b'':
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
        next_header_pos = f.tell() + hdr.size
        # Must begin on an even-byte boundary.
        next_header_pos += next_header_pos % 2

        if limit is not None:
            assert(next_header_pos <= limit)
        f.seek(next_header_pos, 0)
    if rewind:
        f.seek(original_position, 0)

def compute_byte_rate(channels, sample_rate, bits_per_sample):
    return channels * sample_rate * (bits_per_sample // 8)

class FormatError(Exception):
    pass
class AlreadyWritingData(Exception):
    pass
class InvalidPosition(Exception):
    pass

class JWaveSource(object):
    def __init__(self, path):
        self.path = path
        wav = self._w = open(path, 'rb')

        file_header = WAVEHeader_from_src(wav)
        self.assert_fmt(file_header.id == b'RIFF', 'Not RIFF')
        self.assert_fmt(file_header.format == b'WAVE', 'Not WAVE')

        #
        # Quickly scan through all the chunks in the file, noting their
        # identifiers and data locations.
        #
        locators_by_name = collections.defaultdict(list)
        self.locators = locators_by_name

        for locator in ChunkLocators_from_file(wav):
            locators_by_name[locator.header.name].append(locator)

        #
        # There needs to be a single fmt chunk.
        #
        fmt_locators = locators_by_name.get(b'fmt ')
        self.assert_fmt(fmt_locators is not None, 'No "fmt " chunk.')
        self.assert_fmt(len(fmt_locators) == 1, 'Too many "fmt " chunks')
        fmt_locator = fmt_locators[0]

        #
        # Check and break out the format header.
        #
        self.assert_fmt(fmt_locator.header.size >= FMTChunkStruct.size,
            '"fmt " block not big enough to be correct.'
        )
        wav.seek(fmt_locator.offset, 0)
        fmt = FMTChunk_from_src(wav)

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

        #
        # Find the data chunk.
        #
        data_locators = locators_by_name.get(b'data')
        self.assert_fmt(data_locators is not None, 'No "data" chunk.')
        self.assert_fmt(len(data_locators) == 1, 'Too many "data" chunks.')
        data_locator = data_locators[0]

        self._framerate = fmt.SampleRate
        self._nchannels = fmt.NumChannels
        self._sampwidth = fmt.BitsPerSample // 8
        self._framesize = self._nchannels * self._sampwidth
        self._nframes = data_locator.header.size // self._framesize
        self._frameposition = 0

        self.data_offset = data_locator.offset

        #
        # Mark that we aren't yet in the data area.
        #
        self.in_data = False

    #
    # Python wave module compatability.
    #
    def getnframes(self):
        return self._nframes

    def getframerate(self):
        return self._framerate

    def getnchannels(self):
        return self._nchannels

    def getsampwidth(self):
        return self._sampwidth

    def setpos(self, frame_position):
        if not self.in_data:
            self.in_data = True

        if frame_position > self._nframes:
            raise InvalidPosition('Position is too far.')
        elif frame_position < 0:
            raise InvalidPosition('Position is negative.')

        frame_position = int(frame_position)
        self._w.seek(self.data_offset + frame_position * self._framesize, 0)
        self._frameposition = frame_position

    def getpos(self):
        return self._frameposition

    def readframes(self, requested_frame_count):
        if not self.in_data:
            self._w.seek(self.data_offset, 0)
            self.in_data = True

        frames_available = self._nframes - self._frameposition
        frame_count = min(requested_frame_count, frames_available)
        byte_count = frame_count * self._framesize

        data = self._w.read(byte_count)
        assert(len(data) == byte_count)

        self._frameposition += frame_count

        return data

    def chunks(self):
        '''
        Return a dictionary of chunks available in the file.
        
        Entries are indexed by chunk name (as a string). Entry values are
        lists of type ChunkLocator.
        '''
        return self.locators

    def get_chunk(self, chunk_name, instance=None):
        '''
        Return the data portion of the chunk named in chunk_name, and,
        optionally, a specific instance of that chunk. (Numerically indexed.)
        
        Returns the entire data portion of the identified chunk, or
        None if the chunk is not present in the file, or None if there are
        multiple chunks with that identifier and no instance was provided.
        '''
        chunk_locators = self.locators.get(chunk_name)
        if chunk_locators is None:
            return None
        if len(chunk_locators) > 1:
            if instance is not None:
                try:
                    chunk_locator = chunk_locators[instance]
                except (TypeError, IndexError):
                    return None
        else:
            chunk_locator = chunk_locators[0]

        self._w.seek(chunk_locator.offset, 0)
        data = self._w.read(chunk_locator.header.size)

        if self.in_data:
            #
            # We were in the midst of reading frames. Go back to that.
            #
            self.setpos(self._frameposition)

        return data

    @staticmethod
    def assert_fmt(cond, msg):
        if not cond:
            raise FormatError(msg)

class JWaveSink(object):
    def __init__(self, path, rate, channels, depth):
        '''
        Open a WAVE file for writing.
        
        rate -- Sample rate, in hertz. (integer)
        channels -- Number of channels. (integer)
        depth -- Sample depth, in bytes (1 = 8-bit, 2 = 16-bit, 3 = 24-bit)
        '''
        wav = self._w = open(path, 'wb')

        self.total_size = 0
        self.data_allocated = False
        self.locators_by_name = collections.defaultdict(list)

        rate = self.rate = int(rate)
        channels = self.channels = int(channels)
        depth = self.depth = int(depth)
        byte_rate = compute_byte_rate(rate, channels, depth * 8)
        block_align = self.quantum = int(byte_rate // rate)

        #
        # Write the basic WAVE header.
        #
        file_header = WAVEHeader(b'RIFF', WAVEHeader_size(), b'WAVE')
        start_pos = self._allocate_chunk(WAVEHeader_size())
        wav.write(WAVEHeader_to_bytes(file_header))
        assert(start_pos == 0)

        fmt_chunk = FMTChunk(
            AudioFormat=1,
            NumChannels=channels,
            SampleRate=rate,
            ByteRate=byte_rate,
            BlockAlign=block_align,
            BitsPerSample=depth * 8
        )

        self.add_chunk(b'fmt ', FMTChunk_to_bytes(fmt_chunk))

        assert(self.total_size == wav.tell())

        #
        # Add hint for quick header updates.
        #
        self.total_size_offset = start_pos + 4

        self._update_headers()

    def add_chunk(self, name, data):
        '''
        Add a chunk to the file.
        
        Chunk identifiers (names) must remain unique in the file. No two
        chunks with the same name will be allowed.
        
        Cannot be called once sample data has been written. If so, raises
        AlreadyWritingData.
        '''
        if self.data_allocated:
            raise AlreadyWritingData()

        exist = self.locators_by_name.get(name)
        self.assert_fmt(exist is None, 'Duplicate chunk id.')

        hdr = ChunkHeader(name, len(data))
        hdr_bytes = ChunkHeader_to_bytes(hdr)

        #
        # If a chunk occupies an odd number of bytes (counting both
        # the chunk header and its data), it must be followed by a nul byte
        # to ensure that any additional chunks start on an even byte boundary.
        #
        total_bytes = len(data) + len(hdr_bytes)
        padding_needed = total_bytes % 2 != 0

        if padding_needed:
            total_bytes += 1

        pos = self._allocate_chunk(total_bytes)
        data_pos = pos + len(hdr_bytes)

        self._w.write(hdr_bytes)
        self._w.write(data)

        if padding_needed:
            self._w.write(b'\x00')

        self.locators_by_name[name].append(ChunkLocator(data_pos, hdr))

        return pos

    def writeframes(self, frame_data):
        self.writeframes_raw(frame_data)
        self._update_headers()

    def writeframes_raw(self, frame_data):
        if not self.data_allocated:
            #
            # We're need to create a data chunk now.
            #
            pos = self.add_chunk(b'data', b'')
            self.data_size_offset = pos + 4
            self.data_size = 0
            self.data_allocated = True
        data_len = len(frame_data)
        self.assert_fmt(data_len % self.quantum == 0, 'Not aligned.')
        self._w.write(frame_data)
        self.data_size += data_len
        self.total_size += data_len

    def _update_headers(self):
        '''
        Update full file size header and data size header (if allocated).
        
        INTERNAL.
        '''
        f = self._w
        original_pos = f.tell()
        f.seek(self.total_size_offset)
        f.write(Int.pack(self.total_size - 8))
        if self.data_allocated:
            f.seek(self.data_size_offset)
            f.write(Int.pack(self.data_size))
        f.seek(original_pos)

    def _allocate_chunk(self, length):
        assert(not self.data_allocated)
        pos = self.total_size
        self.total_size += length
        return pos

    def close(self):
        self._update_headers()
        self._w.close()
        self._w = None

    def __del__(self):
        if self._w is not None:
            self.close()

    @staticmethod
    def assert_fmt(cond, msg):
        if not cond:
            raise FormatError(msg)

