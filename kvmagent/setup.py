from setuptools import setup, find_packages
import sys, os
import platform

version = '5.7.0'

install_requires = [
    "prometheus_client==0.17.1",
    "libvirt-python>=6.0.0,<=6.2.0",
    "python-cephlibs",
    "setuptools>=65.5.1",
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
