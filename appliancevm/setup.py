from setuptools import setup, find_packages
import sys, os

version = '2.4.0'

setup(name='appliancevm',
      version=version,
      description="zstack appliance vm",
      long_description="""\
zstack appliance vm""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack appliance vm',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      package_data={'':['appliancevm/upgradescripts/*']},
      zip_safe=True,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
