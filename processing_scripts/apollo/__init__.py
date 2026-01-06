#
# Copyright 2019, 2026 Jeremy Cooper.
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
from datetime import datetime, timedelta
import collections

'''
A MissionTimeBasis records the starting time for a mission clock.

A mission clock is a reckoning timescale, often abbreviated as MET
(Mission Elapsed Time) or GET (Ground Elapsed Time).

Generally, the start of a mission's MET is planned far in advance. In some
circumstances, however, the mission doesn't start on time (due to weather,
for example), so another scale known as GET (Ground Elapsed Time) is used
instead.
'''
MissionTimeBasis = collections.namedtuple('MissionTimeBasis',
    'all_balls year')

'''
Elapsed time tuple. Returned from ETFromDatetime().
'''
ET = collections.namedtuple('ElapsedTime',
    'sign hour minute second')

def DatetimeGMTFromIRIG(basis, f):
    '''
    Return a GMT/UTC timestamp (tuple) from an IRIG-B frame.
    
    basis - The time basis for the mission in question.
    f - An IRIG-B frame.
    
    Returns a datetime (in UTC zone)
    '''
    year_ordinal = datetime(year=basis.year + f.years, month=1, day=1).toordinal()
    date = datetime.fromordinal(year_ordinal + f.days - 1)
    return date.replace(
        hour=f.hours,
        minute=f.minutes,
        second=f.seconds
    )

def ETFromDatetimeGMT(basis, dt):
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
    elapsed = dt - basis.all_balls
    return _ETFromDelta(elapsed)

def DatetimeGMTFromET(basis, et):
    '''
    Return a datetime object given a mission basis and elapsed time (GET/MET).
    '''
    delta = timedelta(0, et.hour * 3600 + et.minute * 60 + et.second)
    if et.sign == -1:
        delta *= -1
    return basis.all_balls + delta

def gmt_str(dt):
    return '%04d-%02d-%02d %02d:%02d:%02d Z' % (
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second
    )

def met_str(et):
    neg = '-' if et.sign == -1 else ''
    return '%s%03d:%02d:%02d' % (neg, et.hour, et.minute, et.second)
    
def _ETFromDelta(timedelta):
    '''
    Given a datetime.timedelta, return an Elapsed Time tuple.
    '''
    total_seconds = timedelta.total_seconds()
    if total_seconds < 0:
        sign = -1
        total_seconds *= -1
    else:
        sign = 1
    hours = int(total_seconds) // 3600
    minutes = (int(total_seconds) // 60) % 60
    seconds = int(total_seconds) % 60
    return ET(sign, hours, minutes, seconds)

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
        all_balls=datetime(year=1969,month=7,day=16,hour=13,minute=32),
        year=1969
    ),

    #
    # Apollo 13 range zero time is 19:13:00, April 11, 1970
    # (https://history.nasa.gov/SP-4029/Apollo_13h_Timeline.htm).
    #
    # That is day #101 (one-based)
    #
    'a13' : MissionTimeBasis(
        all_balls=datetime(year=1970,month=4,day=11,hour=19,minute=13),
        year=1970
    ),

    #
    # Apollo 14 range zero time is 21:03:02, January 31, 1971.
    # (https://www.nasa.gov/wp-content/uploads/2023/04/sp-4029.pdf page 176)
    #
    # That is day #31 (one-based)
    #
    'a14' : MissionTimeBasis(
        all_balls=datetime(year=1971,month=1,day=31,hour=21,minute=3,second=2),
        year=1971
    ),

    #
    # Gemini 8 range zero time is 16:41:02, March 16, 1966.
    # That is day #xxx (one-based)
    # (https://en.wikipedia.org/wiki/Gemini_8)
    #
    'g8': MissionTimeBasis(
        all_balls=datetime(year=1966,month=3,day=16,hour=16,minute=41),
        year=1966
    )
}
