#!/usr/bin/env python

def gcd(x, y):
    if y > x:
        x, y = y, x
    while True:
        resid = x % y
        if resid == 0:
            return y
        else:
            x, y = y, resid
