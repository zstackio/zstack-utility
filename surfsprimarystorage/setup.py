from setuptools import setup, find_packages
import sys, os

version = '2.2.0'

setup(name='surfsprimarystorage',
      version=version,
      description="ZStack surfs primary storage",
      long_description="""\
ZStack surfs primary storage""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack surfs',
      author='zhou',
      author_email='zhouhaiping@sursen.net',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
