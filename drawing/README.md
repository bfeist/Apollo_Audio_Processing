# Drawings and such

This directory contains tools which create various illustrations and
animations from the data we have.

## `a13_t911_ekg_telemetry.py`

Using DSP techniques, this tool creats a JSON dump of the EKG and
ZPN data found in tape T911.

## Notes on rendering video

I intend to make the process of generating the video for this data
be completely automated. Doing so involves a lot of components and
moving parts.

### Chrome

Start chrome with the `--allow-file-access-from-files` flag to allow
the video application to save files to disk.

