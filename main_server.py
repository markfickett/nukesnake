#!/usr/bin/env python
"""Run the network server for Nuke Snake.

Example:
  # Run a server with a 200x50 block world.
  %(prog)s --width 200 --height 50
"""
import argparse

import common
import controller
import network


PORT = 9988


if __name__ == '__main__':
  common.ConfigureLogging()
  summary_line, _, main_doc = __doc__.partition('\n\n')
  parser = argparse.ArgumentParser(
      description=summary_line,
      epilog=main_doc,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--host', default='',
      help='Hostname to bind to when serving network play.')
  controller.AddControllerArgs(parser)
  args = parser.parse_args()

  server = network.Server(
      args.host, PORT, args.width, args.height, args.mode, args.round)
  server.ListenAndUpdateForever()
