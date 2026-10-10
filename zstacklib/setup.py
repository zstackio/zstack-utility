from setuptools import setup, find_packages
import sys, os

version = '5.3.0'

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
          'CherryPy==18.8.0', # 3.2.4
          'simplejson==3.18.4', #3.7.3
          'paramiko>=2.0.0',
          'pyparsing==2.4.7',
          'pickledb==0.9.2', # 0.3
          'urllib3==1.26.20',
          'netaddr==0.7.14',
          'Jinja2==3.1.5',
          'Markupsafe==2.1.5',
          'pyroute2==0.7.12',
          'psutil==5.9.8',
          "pyyaml==5.3.1",
          "func_timeout==4.3.5",
          "six>=1.10.0",
          "certifi==2021.5.30",
          "xms-client",
          "setuptools>=65.5.1", #21.0.0
          "cachetools==3.1.1",
          "xxhash==2.0.2",
          "routes==2.4.1",
          "pyudev>=0.18.0",
          "pillow==2.9.0",
          "mock==5.0.2"
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
