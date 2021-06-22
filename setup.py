#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" The setup script."""

from setuptools import find_packages, setup


with open('README.rst', 'rb') as readme_file:
    readme = readme_file.read().decode('utf-8')


setup(
    author='Günther Jena',
    author_email='guenther@jena.at',
    use_scm_version={"write_to": "durand/_version.py"},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    description='CANOpen library providing functionality to implement nodes',
    license='MIT license',
    long_description=readme,
    include_package_data=True,
    keywords='canopen can node ds301',
    name='durand',
    packages=find_packages(include=['durand*']),
    url='https://github.com/semiversus/python-durand',
    zip_safe=False,
)
