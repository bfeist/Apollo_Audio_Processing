'''
Astronaut bio-medical telemetry decoding for Apollo missions.

Accidental telemetry exported to Apollo 13 MOCR audio tapes, discovered by
Jeremy Cooper on 2019-08-21 on tape T911, channel 13, at GET 032:37:07 /
1970-04-14 03:50:01 GMT.

This system is described in AS-508 "MCC/MSFN MISSION CONFIGURATION/SYSTEM
DESCRIPTION". On page 52 of that document there is a table that reads:

IRIG Channel No.   Measurement Name
1                  Unassigned
2                  Command Module Pilot's ZPN
3                  Commander's ZPN
4                  Lunar Module Piolt's ZPN
5                  Commander's EKG
6                  Command Module Pilot's EKG
7                  LM Pilot's EKG

The instruments that made these measurements appear to be described in detail
in the NASA document: https://history.nasa.gov/SP-368/s6ch3.htm

A "ZPN" is a "one impedance pneumograph", or a spring-like device that
measures an astronaut's chest movements, and hence, their breathing patterns.

'''
#from jdsp.blocks import ToneFollower, RationalResampler
#from jdsp.io import WaveSource

from collections import namedtuple

FMTelemetryChannel = namedtuple('FMTelemetryChannel',
    'name frequency bandwidth lpf')

#
# These frequencies were worked out by hand by observing spectrograms
# of the audio snippet we have.
#
configuration = [
    FMTelemetryChannel(name='CMP ZPN',frequency=550.0,bandwidth=100.0,lpf=30),
    FMTelemetryChannel(name='CMDR ZPN',frequency=725.0,bandwidth=100.0,lpf=30),
    FMTelemetryChannel(name='LMP ZPN',frequency=950.0,bandwidth=100.0,lpf=30),
    FMTelemetryChannel(name='CMDR EKG',frequency=1300.0,bandwidth=None,lpf=60),
    FMTelemetryChannel(name='CMP EKG',frequency=1700.0,bandwidth=None,lpf=60),
    FMTelemetryChannel(name='LMP EKG',frequency=2300.0,bandwidth=None,lpf=60)
]

def main(args):
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description='Process Apollo biomed telemetry')
    parser.add_argument('--skip', '-s', metavar='<skip-seconds>', type=float,
        help='Point at which to start processing, in seconds (floating point).')
    parser.add_argument('input', metavar='<input-wav>', type=str,
                        help='Audio file for input.')

    parser.parse_args(args)

if __name__ == '__main__':
    import sys
    main(sys.argv)