from setuptools import setup, find_packages
import sys, os
import platform

version = '4.10.0'

install_requires = [
    "prometheus_client",
    "typing",
    "future",
    "setuptools==21.0.0",   # Keep the same setuptools version as zstacklib
]
if platform.machine() == 'x86_64':
    install_requires.append("grpcio==1.27.2")
    install_requires.append("protobuf==3.12.4")

setup(name='kvmagent',
      version=version,
      description="ZStack KVM agent REST service",
      long_description="""\
ZStack KVM agent REST service""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='zstack kvm python agent REST',
      author='Frank Zhang',
      author_email='xing5820@gmail.com',
      url='http://zstack.org',
      license='Apache License 2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=install_requires,
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
