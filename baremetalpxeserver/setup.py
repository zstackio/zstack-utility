from setuptools import setup, find_packages
import sys, os

version = '3.10.0'

setup(name='baremetalpxeserver',
      version=version,
      description="ZStack baremetal pxeserver agent",
      long_description="""\
ZStack baremetal pxeserver agent""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='baremetal zstack',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      package_data={'':['baremetalpxeserver/ks_tmpl/*']},
      zip_safe=True,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
