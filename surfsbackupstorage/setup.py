from setuptools import setup, find_packages
import sys, os

version = '2.2.0'

setup(name='surfsbackupstorage',
      version=version,
      description="ZStack SURFS backup storage agent",
      long_description="""\
ZStack SURFS backup storage agent""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='surfs zstack',
      author='zhouhaiping',
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
