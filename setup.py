#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" The setup script."""

from setuptools import find_packages, setup


with open('README.rst', 'rb') as readme_file:
    readme = readme_file.read().decode('utf-8')


setup(
    name='durand',
    use_scm_version={"write_to": "src/durand/_version.py"},
    description='CANopen library providing functionality to implement nodes',
    long_description=readme,
    long_description_content_type='text/x-rst',
    url='https://github.com/semiversus/python-durand',
    author='Günther Jena',
    author_email='guenther@jena.at',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    python_requires='>=3.7',
    license='MIT license',
    keywords='canopen can node ds301',
    packages=find_packages('src'),
    package_dir = {'': 'src'},
    zip_safe=False,
)
