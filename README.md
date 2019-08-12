# Apollo13Realtime

Welcome to the Apollo 13 in Real Time processing repository.

1. Install the `jdsp` library in your Python environment.
  
  The defluttering script (the only script at the moment) depends on my "JDSP"
  library, which is included in this repository. You'll need to install it
  into your Python environment, first. It's very easy to do, just use 'pip'
  and you'll get everything you need.

      cd py-jdsp
      sudo pip install .

2. Run `deflutter`

  `deflutter` is the main processing tool. It will deflutter audio tracks
  using a source IRIG-B timecode track for flutter and tracking measurements.
  
  ```
  deflutter
      [-f <max-idle-sec>]
      [-i]
      [-s <skip-sec>]
      [-d <depth>]
      <timecode-audio-in> <timecode-audio-out>
      [<audio-file-1-in> <audio-file-1-out> ...]]
  ```
  
  -f -- Stop processing if more than `<max-idle-sec>` seconds elapse without any detected timecode frames.

  -i -- Invert IRIG-B signal before decoding.
  
  -d -- De-flutter depth (not usually needed, default=1).
  
  -s -- Skip `<skip-sec>` seconds from start of all files before processing.
  ```
