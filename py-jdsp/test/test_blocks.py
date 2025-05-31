import pytest
from jdsp.blocks.ScalableResampler import ScalableResampler


def test_resampler():
    r = ScalableResampler(in_rate=96000, out_rate=96000)
