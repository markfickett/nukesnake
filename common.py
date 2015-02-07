import logging
import os


def MakeGrid(size):
  grid = []
  for x in range(size.x):
    grid.append([None] * size.y)
  return grid


def ConfigureLogging(**kwargs):
  logging.basicConfig(
      format='%(levelname)s %(asctime)s %(filename)s:%(lineno)s: %(message)s',
      level=logging.INFO,
      **kwargs)


# Centralize proto imports which have special requirements.

# For bundled app distribution, include the local directory in LD_LIBRARY_PATH.
resources_dir = os.path.dirname(__file__)
if '.app' in resources_dir:
  os.chdir(resources_dir)
  os.environ['LD_LIBRARY_PATH'] = resources_dir + ':' + os.environ.get(
      'LD_LIBRARY_PATH', '')

# A bottleneck for network communication is (de)serialization of protos when
# the pure-Python implementation is used. Prefer the C++ bindings.
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'cpp'
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION_VERSION'] = '2'

import google.protobuf  # ./setup.sh
from google.protobuf import message
import ai_player_pb2  # protoc --python_out=. *.proto
import game_pb2
import network_pb2

