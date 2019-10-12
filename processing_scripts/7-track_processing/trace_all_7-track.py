__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

inputPath = 'E:/Apollo_13_7-Track/originals_16khz/'
inputPath = '/mnt/e/Apollo_13_7-Track/originals_16khz/'
# outputPath = 'E:/Apollo_13_7-Track/originals_16khz/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))


        wav_filename = subdirname[:-3] + '_TRACK-4_16.wav'

        # command to invoke trace
        # command = "C:\\Utils\\Python27\\python.exe D:\\Apollo_Audio_Processing\\processing_scripts\\deflutter.py timecode -m -F -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=jeremy@simon.baymoo.org' -o E:\\Apollo_13_7-Track\\originals_16khz\\" + subdirname + "\\trace.dat E:\\Apollo_13_7-Track\\originals_16khz\\" + subdirname + "\\" + wav_filename

        command = "python /mnt/d/Apollo_Audio_Processing/processing_scripts/deflutter.py timecode -m -F -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=jeremy@simon.baymoo.org' -o /mnt/hgfs/E/Apollo_13_7-Track/originals_16khz/" + subdirname + "/trace.dat /mnt/hgfs/E/Apollo_13_7-Track/originals_16khz/" + subdirname + "/" + wav_filename

        # # if trace output exists, skip
        if os.path.exists(inputPath + subdirname + '/trace.dat'):
            sys.stdout.write("Trace file EXISTS, SKIPPING: " + subdirname + "\n")
        else:
            print command
            os.system(command)


print "************* DONE"