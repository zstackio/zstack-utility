from setuptools import setup, find_packages
import sys, os

version = '4.4.0'

setup(name='consoleproxy',
      version=version,
      description="zstack console proxy agent",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack console proxy',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
        'websockify',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
