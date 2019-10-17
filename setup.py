# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import os
import sys

from setuptools import find_packages, setup

try:
    from pip.req import parse_requirements
except ImportError:
    # The req module has been moved to pip._internal in the 10
    # release.
    from pip._internal.req import parse_requirements

# Read __version__ from version.py
with open(os.path.join(os.getcwd(), "horsemeat", "version.py")) as f:
    exec(f.read())

requirements = [str(req.req)
    for req in parse_requirements(
        "requirements.txt",
        session="setup.py")]

setup(

    name='horsemeat',

    author="216 Software, LLC",
    author_email="info@216software.com",
    url="https://GitHub.com/216software/horsemeat",
    description='Web framework for the damned.  The mad.',

    version=__version__,

    packages=find_packages(),

    include_package_data=True,

    # package_dir={'horsemeat': 'horsemeat'},

    install_requires=requirements,

    use_2to3=True,

    # test_suite="horsemeat.tests",
    test_suite="nose.collector",
    # test_suite="horsemeat",

    classifiers=[
        'Programming Language :: Python :: 3'
    ],

    scripts=[
        "horsemeat/scripts/make-frippery-project",
    ],
)
