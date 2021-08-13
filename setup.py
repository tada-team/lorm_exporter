from distutils.core import setup
from setuptools import find_packages

setup(
    name='lorm_exporter',
    version='0.14.2',  # lorm 0.12.x
    url='https://github.com/tada-team/lorm_exporter',
    packages=find_packages(),
    package_data={
        'lorm_exporter': ['templates/lorm_exporter/*'],
    },
)
