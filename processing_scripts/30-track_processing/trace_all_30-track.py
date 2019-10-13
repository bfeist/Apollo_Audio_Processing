__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

# inputPath = 'E:/Apollo_13_7-Track/originals_16khz/'
inputPath = '/mnt/e/Apollo_13_Data_Delivery/44.1/denoised/'
# outputPath = 'E:/Apollo_13_7-Track/originals_16khz/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))
        if subdirname != 'old' and subdirname != 'already_defluttered':
            wav_filename = subdirname[:-5] + 'CH1.wav'

            command = "python /mnt/d/Apollo_Audio_Processing/processing_scripts/deflutter.py timecode -m -F -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=bf@benfeist.com' -o " + inputPath + subdirname + "/trace.dat " + inputPath + subdirname + "/" + wav_filename

            # # if trace output exists, skip
            if os.path.exists(inputPath + subdirname + '/trace.dat'):
                sys.stdout.write("Trace file EXISTS, SKIPPING: " + subdirname + "\n")
            else:
                print command
                os.system(command)
    break #prevent going into subfolders

print "************* DONE"