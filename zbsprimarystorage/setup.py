from setuptools import setup, find_packages
import sys, os

version = '5.0.0'

setup(name='zbsprimarystorage',
      version=version,
      description="ZStack zbs primary storage",
      long_description="""\
ZStack zbs primary storage""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack zbs',
      author='Xingwei Yu',
      author_email='xingwei.yu@zstack.io',
      url='https://www.zstack.io',
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
