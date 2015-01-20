# Install dependencies for Nuke Snake.
mkdir build
cd build

# Protobuf
curl -O https://protobuf.googlecode.com/files/protobuf-2.5.0.tar.gz
tar xvfz protobuf-2.5.0.tar.gz
cd protobuf-2.5.0
./configure && make && sudo make install
cd python
python setup.py build && python setup.py test && sudo python setup.py install
cd ..
cd ..

cd ..
