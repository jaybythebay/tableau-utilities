from setuptools import setup

with open('README.md') as f:
    readme = f.read()

setup(
    author="Justin Grilli",
    author_email="justin.grilli@gmail.com",
    license='MIT',
    url='http://pypi.python.org/pypi/tableau-utilities/',
    description='Utility for maintaining Tableau objects',
    long_description=readme,
    long_description_content_type='text/markdown',
    name="tableau_utilities",
    version="2.2.14",
    requires_python=">=3.8",
    packages=[
        'tableau_utilities',
        'tableau_utilities.general',
        'tableau_utilities.tableau_file',
        'tableau_utilities.tableau_server',
        'tableau_utilities.hyper',
        'tableau_utilities.scripts',
    ],
    package_data={'tableau_utilities': ['tableau_file/*.yml']},
    include_package_data=True,
    install_requires=[
        'xmltodict>=0.12.0,<1.0.0',
        'pyyaml>=6.0,<7.0.0',
        'requests>=2.27.1,<3.0.0',
        'pandas>=2.0.0,<3.0.0',
        'tabulate>=0.8.9,<1.0.0',
    ],
    extras_require={"hyper": ['tableauhyperapi<1.0.0']},
    entry_points={
        'console_scripts': [
            'tableau_utilities = tableau_utilities.scripts.cli:main',
        ]
    }
)