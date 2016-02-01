from setuptools import setup, find_packages
import sys, os

version = '1.0'

setup(name='zstacklib',
      version=version,
      description="Python support library for zstack",
      long_description="""\
Python support library for zstack""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack python library',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'CherryPy==3.2.4',
          'simplejson',
          'routes',
          'paramiko',
          'pyparsing<=1.5.7',
          'pickledb',
          'urllib3==1.10.4',
          'netaddr',
          'Jinja2'
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
