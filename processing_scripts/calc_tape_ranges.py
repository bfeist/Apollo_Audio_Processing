import os
import datetime
import math
import wave
import contextlib

# this script uses the decoded IRIG csvs and the CH1 wav files to establish GET start and stop of each tape

def secondsToGET(input_seconds):
    hours = abs(int(input_seconds / 3600))
    minutes = abs(int(input_seconds / 60)) % 60 % 60
    seconds = abs(int(input_seconds)) % 60
    seconds = int(math.floor(seconds))
    hms_string = str(hours).zfill(3) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)
    if input_seconds < 0:
        hms_string = "-" + hms_string
    return hms_string

def GET_to_seconds(locGET):
    splitTimestamp = locGET.split(":")
    totalSeconds = (abs(float(splitTimestamp[0])) * 60 * 60) + (float(splitTimestamp[1]) * 60) + float(splitTimestamp[2])
    if locGET[0] == "-":
        totalSeconds = totalSeconds * -1
    return totalSeconds

wav_length_secs = 0
inputFilePath = "E:/Apollo_13_7-Track/defluttered/"

print
for dirname in os.listdir(inputFilePath):
    # print("dir: " + dirname)
    # if os.path.exists(inputFilePath + dirname + '/BROKEN.txt'):
    if 'orig' in dirname:
        print dirname
    else:
        for filename in os.listdir(inputFilePath + dirname):
            if filename == "markers.all.txt":
                # print("csv filename: " + filename)

                with open(inputFilePath + dirname + "/" + filename) as f:
                    lines = f.read().splitlines()
                    second_line = lines[1]
                    last_line = lines[-1]
                    # print("second line: " + second_line)
                    # print("last line: " + last_line)

                    data_list = second_line.split("\t")
                    seconds_into_file = GET_to_seconds(data_list[1])
                    GET = data_list[0]
                    startGET = secondsToGET(GET_to_seconds(GET) - seconds_into_file)
                    # print(GET + " - " + str(seconds_into_file) + " = StartGET: " + startGET)

                    data_list = last_line.split("\t")
                    last_GET_file_seconds = GET_to_seconds(data_list[1])
                    last_GET = data_list[0]
                    last_GET_to_end_diff = wav_length_secs - last_GET_file_seconds
                    endGET = secondsToGET(GET_to_seconds(last_GET) + last_GET_to_end_diff)
                    # print(last_GET + " + " + str(last_GET_to_end_diff) + " = EndGET: " + endGET)
                    print(dirname + "|" + startGET + "|" + endGET)

            if "TRACK-4" in filename:
                with contextlib.closing(wave.open(inputFilePath + dirname + "/" + filename,'r')) as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    wav_length_secs = frames / float(rate)
                    # print(filename + " wav length: " + str(wav_length_secs))
