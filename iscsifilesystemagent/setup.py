from setuptools import setup, find_packages
import sys, os

version = '2.0.0'

setup(name='iscsifilesystemagent',
      version=version,
      description="The ISCSI primary storage using filesystem as backend",
      long_description="""\
The ISCSI primary storage using filesystem as backend""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack iscsi primarystorage',
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
