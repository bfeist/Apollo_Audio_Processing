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
from math import gcd
import numpy

class SimpleResampler(object):
    def __init__(self, in_rate, out_rate):
        assert(out_rate > in_rate)
        g = gcd(out_rate, in_rate)
        self.top = out_rate / g
        self.step = in_rate / g
        self.z = None
        self.have_z = False
        self.have_zp1 = False
        self.delta = 0
        self.cur = 0
    
    def process(self, data):
        dlen = len(data)
        i = 0
        z = self.z
        out = []
        have_z = self.have_z
        have_zp1 = self.have_zp1
        delta = self.delta
        cur = self.cur
        step = self.step
        top = self.top
        while i < dlen:
            if not have_z:
                z = data[i]
                have_z = True
                have_zp1 = False
                i += 1
                continue
            elif not have_zp1 and cur > 0:
                delta = data[i] - z
                have_zp1 = True
            out.append(z + delta * (cur / top))
            cur += step
            if cur >= top:
                cur -= top
                have_z = False
        self.z = z
        self.delta = delta
        self.have_z = have_z
        self.have_zp1 = have_zp1
        self.cur = cur
        return numpy.array(out, dtype='float')
