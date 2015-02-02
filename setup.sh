#!/bin/bash
# Install dependencies for Nuke Snake.
set -e

mkdir build
# Sudo now to avoid password prompt later.
sudo touch build
cd build

# Protobuf
VER=2.6.1
curl -L -O https://github.com/google/protobuf/releases/download/v${VER}/protobuf-${VER}.tar.gz
tar xvfz protobuf-${VER}.tar.gz

cd protobuf-${VER}
./configure
make
make check
sudo make install
# If this fails (errors about libprotobuf.so.9), check your LD_LIBRARY_PATH.
# stackoverflow.com/questions/17889799/libraries-in-usr-local-lib-not-found
protoc --version

cd python
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=cpp
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION_VERSION=2
# If the build fails, you may need to install setuptools:
# pypi.python.org/pypi/setuptools
python setup.py build
# This may fail if an older version of protobuf is installed; try removing it.
python setup.py google_test
python setup.py test --cpp_implementation
sudo python setup.py install --cpp_implementation
cd ..
cd ..

cd ..
