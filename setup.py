from setuptools import find_packages, setup

from horsemeat import __version__

setup(

    name='horsemeat',

    author="216 Software, LLC",
    author_email="info@216software.com",
    url="https://github.com/216software/horsemeat",

    version=__version__,

    packages=find_packages(),

    include_package_data=True,

    package_dir={'horsemeat': 'horsemeat'},

    install_requires=[
        'decorator',
        'PyYAML',
        'jinja2==2.6',
        'psycopg2',
        'pyrax',
        'Werkzeug',
        'clepy',
    ],
)
