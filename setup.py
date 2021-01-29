from distutils.core import setup
from setuptools import find_packages

setup(
    name='lorm_exporter',
    version='0.6.2',
    url='https://github.com/tada-team/lorm_exporter',
    packages=find_packages(),
    package_data={
        'lorm_exporter': ['templates/lorm_exporter/*'],
    },
)
