__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

inputPath = '/mnt/e/Apollo_13_Data_Delivery/44.1/denoised/'
outputPath = '/mnt/e/Apollo_13_Data_Delivery/44.1/defluttered/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))
        outputSubdirName = "D" + subdirname

        for i in range(1, 30):
            wav_filename = subdirname[:-5] + 'CH' + str(i) + '.wav'
            if subdirname != 'old' and subdirname != 'already_defluttered':
                if os.path.exists(inputPath + subdirname + '/' + wav_filename):
                    command = "python /mnt/d/Apollo_Audio_Processing/processing_scripts/deflutter.py trace -T 'Version=a1f2a3a759980d7e927a0be4b2dcb18776fa0eef;Operator=bf@benfeist.com' " + inputPath + subdirname + "/trace.dat " + inputPath + subdirname + "/" + wav_filename + " " + outputPath + outputSubdirName + "/D" + wav_filename

                    # if output already exists, skip
                    if os.path.exists(outputPath + outputSubdirName + '/D' + wav_filename):
                        print "Defluttered file EXISTS, SKIPPING: " + outputSubdirName + '/D' + wav_filename
                    else:
                        if not os.path.exists(outputPath + outputSubdirName):
                            os.makedirs(outputPath + outputSubdirName)
                        print command
                        os.system(command)
    break #prevent going into subfolders

print "************* DONE"