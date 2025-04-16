# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import os
import sys

from setuptools import find_packages, setup

# Read __version__ from version.py
with open(os.path.join(os.getcwd(), "horsemeat", "version.py")) as f:
    exec(f.read())

setup(

    name='horsemeat',

    author="216 Software, LLC",
    author_email="info@216software.com",
    url="https://github.com/216software/horsemeat",
    description='Web framework for the damned.  The mad.',

    version=__version__,

    packages=find_packages(),

    include_package_data=True,

    # package_dir={'horsemeat': 'horsemeat'},

    # install_requires=requirements,

    install_requires=[
        "Jinja2>=2.6",
        "PyYAML>=3.10",
        "Werkzeug>=0.10.1",
        "decorator>=3.4.0",
        "psycopg2>=2.7",
        # "nose>=1.3.3",
        "gunicorn",
    ],

    # use_2to3=True,

    # test_suite="horsemeat.tests",
    # test_suite="nose.collector",
    # test_suite="horsemeat",

    classifiers=[
        'Programming Language :: Python :: 3'
    ],

    scripts=[
        "horsemeat/scripts/make-frippery-project",
    ],
)
