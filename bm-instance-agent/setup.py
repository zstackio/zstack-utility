import os
import setuptools


def read_requirements():
    requirements = []
    path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(path, 'r') as f:
        for line in f.readlines():
            if line and not line.startswith('#'):
                requirements.append(line)
    return requirements


setuptools.setup(install_requires=read_requirements())
