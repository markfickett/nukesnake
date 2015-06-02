#!/usr/bin/env python
"""Starts a Nuke Snake client to connect to a running server and play the game.

Example:
  # Connect to an available network server on localhost.
  %(prog)s
"""

import argparse

import client
import common
import controller
import network


if __name__ == '__main__':
  log_filename = '/tmp/nukesnake_client_log.txt'
  print 'log file %s' % log_filename
  common.ConfigureLogging(filename=log_filename)

  summary_line, _, main_doc = __doc__.partition('\n\n')
  parser = argparse.ArgumentParser(
      description=summary_line,
      epilog=main_doc,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '-a', '--ai', action='append', default=[],
      help='Names for AI players to add to the game.')
  parser.add_argument(
      '--host', default='localhost',
      help='Server to connect to for network play.')
  parser.add_argument(
      '-n', '--no-network', action='store_true', dest='nonetwork',
      help='Run the game server in the same process as the client.')
  controller.AddControllerArgs(parser)
  args = parser.parse_args()

  if args.nonetwork:
    game_server = network.LocalThreadClient(
        args.width, args.height, args.mode, args.round)
    game_server.daemon = True
    game_server.start()
  else:
    game_server=None

  client.RunClient(args.host, args.ai, server=game_server)
