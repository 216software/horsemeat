from setuptools import find_packages, setup

setup(

    name='horsemeat',

    version='0.1.1',

    packages=find_packages(),

    include_package_data=True,

    package_dir={'horsemeat': 'horsemeat'},

    install_requires=[
        'decorator',
        'PyYAML',
        'jinja2',
        'psycopg2',
        'pyrax',
        'Werkzeug',
    ],

)
