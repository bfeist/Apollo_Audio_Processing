__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

# inputPath = 'E:/Apollo_13_7-Track/originals_16khz/'
# outputPath = 'E:/Apollo_13_7-Track/defluttered/'
inputPath = '/mnt/hgfs/E/Apollo_13_7-Track/originals_16khz/'
outputPath = '/mnt/hgfs/E/Apollo_13_7-Track/defluttered/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))

        for i in range(3, 7):
            wav_filename = subdirname[:-3] + '_TRACK-' + str(i) + '_16.wav'

            # command to invoke trace
            # command = "C:\\Utils\\Python27\\python.exe D:\\Apollo_Audio_Processing\\processing_scripts\\deflutter.py trace -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=jeremy@simon.baymoo.org' E:\\Apollo_13_7-Track\\originals_16khz\\" + subdirname + "\\trace.dat E:\\Apollo_13_7-Track\\originals_16khz\\" + subdirname + "\\" + wav_filename + " E:\\Apollo_13_7-Track\\defluttered\\" + subdirname + "\\D" + wav_filename

            command = "python /mnt/hgfs/D/Apollo_Audio_Processing/processing_scripts/deflutter.py trace -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=jeremy@simon.baymoo.org' /mnt/hgfs/E/Apollo_13_7-Track/originals_16khz/" + subdirname + "/trace.dat /mnt/hgfs/E/Apollo_13_7-Track/originals_16khz/" + subdirname + "/" + wav_filename + " /mnt/hgfs/E/Apollo_13_7-Track/defluttered/" + subdirname + "/D" + wav_filename

            # # if trace output exists, skip
            if os.path.exists(outputPath + subdirname + '/D' + wav_filename):
                print "Defluttered file EXISTS, SKIPPING: " + subdirname + '/D' + wav_filename
            else:
                if not os.path.exists(outputPath + subdirname):
                    os.makedirs(outputPath + subdirname)
                print command
                os.system(command)


print "************* DONE"