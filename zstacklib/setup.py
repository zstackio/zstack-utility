from setuptools import setup, find_packages
import sys, os

version = '4.6.0'

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
          'simplejson==3.7.3',
          'routes==2.1',
          'paramiko==1.15.2',
          'pyparsing<=1.5.7',
          'pickledb==0.3',
          'urllib3==1.10.4',
          'netaddr==0.7.14',
          'Jinja2==2.7.3',
          'pyroute2==0.5.14',
          'psutil==5.0.1',
          "beeprint==2.4.7",
          "pyyaml",
          "func_timeout==4.3.5",
          "six==1.9.0",
          "certifi==2021.5.30",
          "xms-client",
          "python-dateutil",
          "enum34==1.1.6",
          "cachetools==3.1.1",
          "xxhash==2.0.2"
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
