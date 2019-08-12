from setuptools import setup

setup(name='jdsp',
      version='0.2',
      py_modules=[
          'jdsp.util',
          'jdsp.io.WaveSource',
          'jdsp.io.WaveSink',
          'jdsp.blocks.HighPassFilter',
          'jdsp.blocks.SimpleResampler',
          'jdsp.blocks.ZeroCrossDetector'
      ],
      packages = [ 'jdsp' ],
      package_dir = { 'jdsp' : 'lib' },
      install_requires=[
          'numpy(>=1.10)',
          'scipy(>=0.16.0)'
      ]
)
