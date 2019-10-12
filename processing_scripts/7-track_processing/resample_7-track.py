__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

inputPath = 'E:/Apollo_13_7-Track/originals/'
outputPath = 'E:/Apollo_13_7-Track/originals_16khz/'

for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all filenames.
    for subdirname in dirnames:
        # print(subdirname)
        # print(os.path.join(dirname, subdirname))

        for i in range(3, 7):
            wav_filename = subdirname + '_TRACK-' + str(i)
            # print wav_filename

            # FFMPEG command to resample to 16000Hz
            command = 'ffmpeg -i ' + inputPath + subdirname + '/' + wav_filename + '.wav -ar 16000 ' + outputPath + subdirname + "_16/" + wav_filename + "_16.wav"

            # FFMPEG command to concatenate
            # command = 'ffmpeg -f concat -safe 0 -i filelist.txt -c copy ' + outputPath + outputFoldername + outputFilename


            # Create folders and execute
            if os.path.exists(outputPath + subdirname + "_16/" + wav_filename + "_16.wav"):
                sys.stdout.write("EXISTS, SKIPPING: " + command + "\n")
            else:
                if not os.path.exists(outputPath + subdirname + "_16/"):
                    os.makedirs(outputPath + subdirname + "_16/")
                sys.stdout.write(command)
                os.system(command)


print "************* DONE"