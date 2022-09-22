from setuptools import setup, find_packages
import sys, os

version = '4.5.0'

setup(name='zstackcli',
      version=version,
      description="zstack cli console",
      long_description="""\
zstack cli console""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack api cli python',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'termcolor'
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      data_files=[('/usr/bin', ['zstack-cli'])]
      )
