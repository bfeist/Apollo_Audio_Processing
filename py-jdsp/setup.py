from setuptools import setup

setup(name='jdsp',
      version='0.6.3',
      py_modules=[
          'jdsp.util.DelayBuffer',
          'jdsp.util.gcd',
          'jdsp.io.WaveSource',
          'jdsp.io.WaveSink',
          'jdsp.blocks.HighPassFilter',
          'jdsp.blocks.SimpleResampler',
          'jdsp.blocks.ZeroCrossDetector',
          'jdsp.blocks.RationalResampler',
          'jdsp.blocks.ScalableResampler',
          'jdsp.blocks.CyclicFilter',
          'jdsp.blocks.ToneFollower',
      ],
      packages = [ 'jdsp' ],
      package_dir = { 'jdsp' : 'lib' },
      install_requires=[
          'numpy(>=1.10)',
          'scipy(>=0.16.0)',
          'numba(>=0.40)'
      ]
)
