# Apollo13Realtime

Welcome to the Apollo 13 in Real Time processing repository.

The processing scripts in thie repository depend on a common DSP library
that I have written, `jdsp`. You'll need to have `jdsp` installed in your Python
environment before you begin. It's very easy to do, just use 'pip' and you'll
get everything you need.

      cd py-jdsp
      sudo pip install .

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

You can use `deflutter.py` to remove flutter and precisely retime audio tracks, provided one of
those tracks is a dedicated IRIG-B timecode stream.

```
deflutter
    [-f <max-idle-sec>]
    [-i]
    [-s <skip-sec>]
    [-d <depth>]
    <timecode-audio-in> <timecode-audio-out>
    [<audio-file-1-in> <audio-file-1-out> ...]]
```
  
`-f` -- Stop processing if more than `<max-idle-sec>` seconds elapse without any detected timecode frames.

`-i` -- Invert IRIG-B signal before decoding.
  
`-d` -- De-flutter depth (not usually needed, default=1).
  
`-s` -- Skip `<skip-sec>` seconds from start of all files before processing.
  ```
