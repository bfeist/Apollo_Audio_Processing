#
# Copyright 2019 Jeremy Cooper.
#
# This file is unpublished proprietary source code. It is licensed
# for use by members of the the Apollo Audio project ("ApolloAudio"),
# who are determined at the sole discretion of Ben Feist, for use on archival
# audio produced by NASA's Apollo programs ("Apollo Material"), determined
# at the sole discretion of Jeremy Cooper.
#
# Any use outside of ApolloAudio, and/or on material other than Apollo
# Material is prohibited.
#
'''
Apollo Mission module - Time handling

This module helps with conversion between mission time formats and ground-based
time (such as GMT and UTC) for various Apollo missions.


'''
from datetime import datetime
import collections

'''
A MissionTimeBasis records the starting time for a mission clock.

A mission clock is a reckoning timescale, often abbreviated as MET
(Mission Elapsed Time) or GET (Ground Elapsed Time).

Generally, the start of a mission's MET is planned far in advance. In some
circumstances, however, the mission doesn't start on time (due to weather,
for example), so another scale known as GET (Ground Elapsed Time) is used
Each mission has its officially planned start time
'''
MissionTimeBasis = collections.namedtuple('MissionTimeBasis',
    'all_balls year')

'''
GMT timestamp tuple. Returned from GMTFromIRIG().
'''
Timestamp = collections.namedtuple('Timestamp',
    'year month day hour minute second')

'''
Elapsed time tuple. Returned from MissionTimeFromIRIG().
'''
ET = collections.namedtuple('ElapsedTime',
    'sign hour minute second')

def GMTFromIRIG(basis, f):
    '''
    Return a GMT/UTC timestamp (tuple) from an IRIG-B frame.
    
    basis - The time basis for the mission in question.
    f - An IRIG-B frame.
    
    Returns (year, month, day, hours, minutes, seconds).

    year -- Common Era based (1 CE == 1 AD)
    month -- 1-based (January == 1)
    day -- 1-based
    '''
    year_ordinal = datetime(basis.year + f.years, 1, 1).toordinal()
    date = datetime.fromordinal(year_ordinal + f.days - 1)
    return Timestamp(
        date.year,
        date.month,
        date.day,
        f.hours,
        f.minutes,
        f.seconds
    )

def MissionTimeFromDatetimeGMT(basis, ts):
    '''
    Return a mission time (MET/GET) time from a GMT-based datetime.

    basis - The time basis for the mission in question.
    ts - A datetime.datetime GMT timestamp.
    
    Returns (sign, hours, minutes, seconds).
    
    sign -- 1 if ET is positive, -1 if negative.
    hours, minutes, seconds will always be >= 0.
    
    NOTES:
    The Apollo missions referenced "GMT" rather than "UTC". That naming is
    retained here.
    '''
    year_day = ts.timetuple().tm_yday
    year_seconds = date_to_seconds(
        (ts.year - basis.year) * 365 + year_day,
        ts.hour,
        ts.minute,
        ts.second
    )
    return _MissionTimeFromYS(basis, year_seconds)
    
def MissionTimeFromIRIG(basis, f):
    '''
    Return a mission time (MET/GET) time tuple from an IRIG-B frame.

    basis - The time basis for the mission in question.
    f - An IRIG-B frame.
    
    Returns (sign, hours, minutes, seconds).
    
    sign -- 1 if ET is positive, -1 if negative.
    hours, minutes, seconds will always be >= 0.
    '''
    year_seconds = date_to_seconds(
        f.years * 365 + f.days,
        f.hours,
        f.minutes,
        f.seconds
    )
    return _MissionTimeFromYS(basis, year_seconds)

def _MissionTimeFromYS(basis, year_seconds):
    mission_seconds = year_seconds - basis.all_balls
    if mission_seconds < 0:
        mission_seconds *= -1
        sign = -1
    else:
        sign = 1
    hours = mission_seconds // 3600
    minutes = (mission_seconds // 60) % 60
    seconds = mission_seconds % 60
    return ET(sign, hours, minutes, seconds)

def gmt_from_nasa(h, m, s, basis):
    mission_seconds = date_to_seconds(0, h, m, s)
    year_seconds = mission_seconds + basis.all_balls
    s = year_seconds % 60
    m = (year_seconds // 60) % 60
    h = (year_seconds // 3600) % 24
    d = (year_seconds // 86400) % 365
    return '%02dd %02dh %02dm %02ds' % (d, h, m, s)

def gmt_str(timestamp):
    return '%04d-%02d-%02d %02d:%02d:%02d Z' % timestamp

def met_str(et):
    neg = '-' if et.sign == -1 else ''
    return '%s%03d:%02d:%02d' % (neg, et.hour, et.minute, et.second)
    
def date_to_seconds(day, hour, minute, second):
    return ((((day * 24) + hour) * 60 + minute) * 60) + second

'''
A database of missions and their time bases.
'''
TimeBases = {
    #
    # Apollo 11 range zero time is 13:32:00, July 16, 1969
    # That is day #197 (one-based)
    #
    'a11' : MissionTimeBasis(
        all_balls=date_to_seconds(197, 13, 32, 0),
        year=1969
    ),

    #
    # Apollo 13 range zero time is 19:13:00, April 11, 1970
    # (https://history.nasa.gov/SP-4029/Apollo_13h_Timeline.htm).
    #
    # That is day #101 (one-based)
    #
    'a13' : MissionTimeBasis(
        all_balls=date_to_seconds(101, 19, 13, 0),
        year=1970
    )
}
