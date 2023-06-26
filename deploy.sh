#!/bin/sh

python3 -m pip install setuptools wheel
python3 -m pip install --upgrade setuptools wheel
python3 -m pip install twine
python3 -m pip install --upgrade twine
python3 setup.py sdist bdist_wheel
python3 -m twine upload dist/*
