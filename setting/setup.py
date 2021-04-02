from setuptools import setup, find_packages
import sys, os

version = '0.1.0'

setup(name='setting',
      version=version,
      description="ZStack setting tool",
      long_description="""\
ZStack setting tool""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack python setting tool',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      package_data= {
          'setting' : ['property-templates/*.xml', 'resource/puppet/**'],
      },
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          "argparse==1.3.0",
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
