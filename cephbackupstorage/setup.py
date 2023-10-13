from setuptools import setup, find_packages
import sys, os

version = '4.8.0'

setup(name='cephbackupstorage',
      version=version,
      description="ZStack CEPH backup storage agent",
      long_description="""\
ZStack CEPH backup storage agent""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='ceph zstack',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
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
