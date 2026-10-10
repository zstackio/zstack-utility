from setuptools import setup, find_packages
import sys, os

version = '5.3.0'

setup(name='zstackctl',
      version=version,
      description="zstack management tool",
      long_description="""\
zstack management tool""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      package_data={'':['zstack_ctl/conf/*']},
      zip_safe=True,
      install_requires=[
          'termcolor',
          'simplejson==3.18.4',
          'configobj==5.0.9',
          'pyyaml==5.3.1',
          'ansible==9.13.0',
          'pyroute2>=0.5.14',
          'pycryptodome==3.19.1',
          'pyOpenSSL', # TODO upgrade
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      data_files=[('/usr/bin', ['zstack-ctl'])]
      )
