from setuptools import find_packages, setup

from horsemeat import __version__

setup(

    name='horsemeat',

    version='0.2.2',

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
    ],
)
