#!/usr/bin/python
"""Interactive server and client startup script.

See main_* for separate server and client starters.
"""

import os
import multiprocessing

# For bundled app distribution, include the local directory in LD_LIBRARY_PATH.
resources_dir = os.path.dirname(__file__)
if '.app' in resources_dir:
  os.chdir(resources_dir)  # Allow a relative paty for the dylib, see Makefile.
  os.environ['LD_LIBRARY_PATH'] = resources_dir + ':' + os.environ.get(
      'LD_LIBRARY_PATH', '')

from common import game_pb2
import client
import common
import network

common.ConfigureLogging(filename='/tmp/nukesnake.log')

print 'Welcome to Nuke Snake by Mark Fickett. markfickett.com/nukesnake'
print (
    'Enter a name or IP address to join a game on another computer. '
    'Just hit enter to run a local server.')
hostname = raw_input('Hostname: [start a local server] ')

if not hostname:
  print (
      'In BATTLE, the last player alive wins. In CLEAR_MINES, one or more '
      'players collaborate to explode all the mines and pick up or explode '
      'all the nukes.')
  mode = game_pb2.Mode.Id.Value(raw_input('Game mode? [BATTLE] ') or 'BATTLE')
  width, height = map(int, (raw_input(
      'World size width x height? [100 30] ') or '100 30').split())
  starting_round = int(raw_input(
      'Starting round (affects speed and AI difficulty)? [0] ') or '0')
  def RunServer(*args):
    server = network.Server(*args)
    server.ListenAndUpdateForever()
  server_process = multiprocessing.Process(
      target=RunServer,
      args=('', network.PORT, width, height, mode, starting_round))
  server_process.daemon = True
  server_process.start()

  print (
      'Would you like an computer-controlled AIs to compete with? Enter as '
      'many names as you like separated by spaces.')
  ai_names = raw_input('AIs? [no AIs] ').split()
else:
  ai_names = []

client.RunClient(hostname or 'localhost', ai_names)
