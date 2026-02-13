# Apollo_Audio_Processing

Welcome to the Apollo audio processing repository.

## Prerequisites / dependencies

First, make sure you have `uv` installed. Then create a virtual environment and install dependencies:

      uv venv
      source .venv/bin/activate  # On Windows: .venv\Scripts\activate
      uv pip install -r requirements.txt
      uv pip install ./py-jdsp

The processing scripts in this repository also depend on a common DSP library
that I have written, `jdsp`, which is installed in the final step above.

### Recent gotchas

* 2025-05-29: scipy, one of the dependencies required to set up this code,
  requires a Fortran compiler. If you encounter an error while running the
  installation step above, try installing a Fortran compiler (such as
  `gfortran`) on your system and try the installation step again.

## IRIG-B processing / tagging

You can use `irig_b.py` to inspect an IRIG-B timecode stream and generate labels for
the timecode frames it finds. The information it generates will be written to stdout.

```
irig_b
    [-i]
    [-l]
    [-b <base>]
    <wav-file>
```
`-i`  Invert audio before processing.

`-l`  Write Audacity-compatible labels on output.

`-b`  Translate time for specific mission basis. (Available missions: 'a11', 'a13').

*Note: this script is also incorporated as module for the deflutter script. Keep them together.*

## Tape defluttering

You can use `deflutter.py` to remove flutter and precisely re-time audio tracks, provided you have
an appropriate IRIG-B timing source. An IRIG-B timing source can either be a WAV file known to
carry IRIG-B timecode, or a "trace" file from a previously processed IRIG-B WAV file. To process
an IRIG-B WAV file so that it can be used as a trace for other audio files, use `timecode` mode.
To use a trace file, use `trace` mode.

```
    deflutter timecode [options] [<audio-files>]
or: deflutter trace    [options] <audio-files>
```

### Timecode mode

```
timecode [-f <max-idle>] [-i] [-s <offset>] [-o <trace-data-out>]
         [-t <timecode-audio-out>]
         <timecode-audio-in>
         [ <audio-file-1-in> <audio-file-1-out>
          [<audio-file-2-in> <audio-file-2-out>] [...] ]
```

In timecode processing mode, the tape flutter and wow are extracted
from an IRIG-B audio track. The flutter measurements can then be
applied immediately to other audio tracks, or they can be saved
to a trace file, where they can be loaded and used for a later job.

`-i`

Invert IRIG-B signal before decoding.

`-s <offset>`

Skip `<offset>` seconds from start of file. (This skip value will be written to the
generated trace file, if one has been specified.)

`-f <max-idle>`

Stop processing if more than <max-idle> seconds elapse without any detected timecode frames.
(floating point).

`-t <timecode-audio-out>`

Deflutter the timecode track and write and write it to `<timecode-audio-out>`. (Timecode
track is not defluttered by default).

## Trace mode

```
trace <trace-data-file>`
      <audio-file-1-in> <audio-file-1-out>
     [<audio-file-2-in> <audio-file-2-out>] ...
```

The flutter measurements from `<trace-data-file>` will be used to deflutter all of the files provided on the command line.
