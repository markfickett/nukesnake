#!/usr/bin/python
"""Interactive server and client startup script."""

import os
import multiprocessing

# For bundled app distribution, include the local directory in LD_LIBRARY_PATH.
resources_dir = os.path.dirname(__file__)
if '.app' in resources_dir:
  os.chdir(resources_dir)
  os.environ['LD_LIBRARY_PATH'] = resources_dir + ':' + os.environ.get(
      'LD_LIBRARY_PATH', '')

from common import game_pb2
import client
import common
import network

common.ConfigureLogging(filename='/tmp/nukesnake.log')

def RunServer(*args):
  server = network.Server(*args)
  server.ListenAndUpdateForever()

server_process = multiprocessing.Process(
    target=RunServer,
    args=('', network.PORT, 100, 30, game_pb2.Mode.CLEAR_MINES, 10))
server_process.daemon = True
server_process.start()

client.RunClient('localhost', ['Guice'])
