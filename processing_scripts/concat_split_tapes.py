__author__ = 'Feist'
# import requests
import re
import sys
import os
import re

def get_arg(index):
    try:
        sys.argv[index]
    except IndexError:
        return ''
    else:
        return sys.argv[index]

tape = get_arg(1)

inputPath = 'O:/Apollo 13 30-Track/44.1/original/'
# inputPath = 'E:/Apollo_13_Data_Delivery/44.1/original/'
outputPath = 'D:/concatenated/'
# outputPath = 'F:/concat/'


firstmatch = True
first_match_part_num = 0
first_match_part_path = ''
first_match_tape_type = ''
second_match_part_num = 0
second_match_part_path = ''

# This just figures out which path is part 1 of the split tape, and which is part 2
for dirname, dirnames, filenames in os.walk(inputPath):
    # print path to all subdirectories first.
    for subdirname in dirnames:
        # print(os.path.join(dirname, subdirname))
        match = re.match(r"A13_%s_(HR.*?)_.*P(\d)" % tape, subdirname)
        if match:
            if firstmatch:
                first_match_part_num = int(match.group(2))
                first_match_tape_type = match.group(1)
                first_match_part_path = os.path.join(dirname, subdirname)
                firstmatch = False
            else:
                second_match_part_num = int(match.group(2))
                second_match_part_path = os.path.join(dirname, subdirname)
                if first_match_part_num > second_match_part_num:  #switch them around if wrong order
                    temp_part_path = second_match_part_path
                    second_match_part_path = first_match_part_path
                    first_match_part_path = temp_part_path
                break

print ("first part path: " + first_match_part_path)
print ("second part path: " + second_match_part_path)


# Now get all the wav files in the first part path
part1FilePath = ''
part2FilePath = ''
for dirname, dirnames, filenames in os.walk(first_match_part_path):
    # print path to all filenames.
    for filename in filenames:
        if re.search(".*wav", filename):
            channelmatch = re.match(".*_CH(.+?)_.*\.wav", filename)
            # print(os.path.join(dirname, filename))
            # print channelmatch.group(1)
            part1ChannelNumber = channelmatch.group(1)
            part1FilePath = os.path.join(dirname, filename)

            # create an output filename based on the part 1 name
            outputFilename = "A13_" + tape + "_" + first_match_tape_type + "_CH" + part1ChannelNumber + ".wav"
            outputFoldername = "A13_" + tape + "_" + first_match_tape_type + "_16khz/"

            # Now find the matching second part file of that channel number
            for dirname2, dirnames2, filenames2 in os.walk(second_match_part_path):
                for filename2 in filenames2:
                    if re.search(".*wav", filename2):
                        channelmatch = re.match(".*_CH(.+?)_.*?\.wav", filename2)
                        part2ChannelNumber = channelmatch.group(1)
                        if int(part1ChannelNumber) == int(part2ChannelNumber):
                            part2FilePath = os.path.join(dirname2, filename2)
                            break

            # Write the FFMPEG file list temporary file used for FFMPEG concatenation
            outputFilelist = open("filelist.txt", "w")
            # sys.stdout.write("_".join(map(str, row)) + "\n")
            outputFilelist.write("file '" + part1FilePath + "'\n")
            outputFilelist.write("file '" + part2FilePath + "'\n")
            outputFilelist.close()

            print ("\tfirst file path: " + part1FilePath)
            print ("\tsecond file path: " + part2FilePath)

            # FFMPEG command to concatenate and resample to 16000Hz
            command = 'ffmpeg -f concat -safe 0 -i filelist.txt -ar 16000 ' + outputPath + outputFoldername + outputFilename

            # FFMPEG command to concatenate
            # command = 'ffmpeg -f concat -safe 0 -i filelist.txt -c copy ' + outputPath + outputFoldername + outputFilename


            # Create folders and execute
            if os.path.exists(outputPath + outputFoldername + outputFilename):
                sys.stdout.write("EXISTS, SKIPPING: " + command + "\n")
            else:
                if not os.path.exists(outputPath + outputFoldername):
                    os.makedirs(outputPath + outputFoldername)
                sys.stdout.write(command)
                os.system(command)


print "************* DONE"