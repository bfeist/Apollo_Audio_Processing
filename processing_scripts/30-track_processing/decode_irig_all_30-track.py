__author__ = 'Feist'
# import requests
import re
import sys
import os
import re
import glob

inputPath = '/mnt/e/Apollo_13_Data_Delivery/44.1/defluttered/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))
        wav_filename = subdirname[:-5] + 'CH1.wav'

        command = "python /mnt/d/Apollo_Audio_Processing/processing_scripts/irig_b.py -f b -b a13 -a " + inputPath + subdirname + "/" + wav_filename + " > " + inputPath + subdirname + "/markers.all.txt"

        # # if marker output exists, skip
        if os.path.exists(inputPath + subdirname + '/BROKEN.txt'):
            print "deflutter BROKEN, SKIPPING: " + subdirname
        elif os.path.exists(inputPath + subdirname + '/markers.all.txt'):
            print "marker file EXISTS, SKIPPING: " + subdirname
        elif glob.glob(inputPath + subdirname + '/*.csv'):
            print "csv marker file EXISTS, SKIPPING: " + subdirname
        else:
            print command
            os.system(command)
    break #prevent going into subfolders

print "************* DONE"