__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

# inputPath = 'E:/Apollo_13_7-Track/defluttered/'
inputPath = '/mnt/hgfs/E/Apollo_13_7-Track/defluttered/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))


        wav_filename = "D" + subdirname[:-3] + '_TRACK-4_16.wav'

        # command to invoke trace
        # command = "C:\\Utils\\Python27\\python.exe D:\\Apollo_Audio_Processing\\processing_scripts\\irig_b.py -f b -b a13 -a " + "E:\\Apollo_13_7-Track\\defluttered\\" + subdirname + "\\" + wav_filename + " > E:\\Apollo_13_7-Track\\defluttered\\" + subdirname + "\\" "markers.all.txt"

        command = "python /mnt/hgfs/D/Apollo_Audio_Processing/processing_scripts/irig_b.py -f b -b a13 -a " + inputPath + subdirname + "/" + wav_filename + " > " + inputPath + subdirname + "/markers.all.txt"

        # # if marker output exists, skip
        if os.path.exists(inputPath + subdirname + '/BROKEN.txt'):
            print "deflutter BROKEN, SKIPPING: " + subdirname
        elif os.path.exists(inputPath + subdirname + '/markers.all.txt'):
            print "marker file EXISTS, SKIPPING: " + subdirname
        else:
            print command
            os.system(command)


print "************* DONE"