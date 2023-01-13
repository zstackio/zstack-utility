from setuptools import setup, find_packages
import sys, os

version = '4.6.0'

setup(name='appbuildsystem',
      version=version,
      description="ZStack Application Build System",
      long_description="""\
ZStack Application Build System agent""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='application buildsystem zstack',
      author='mingjian.deng',
      author_email='mingjian.deng@zstack.io',
      url='https://zstack.io',
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
