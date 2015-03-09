#!/usr/bin/env python
"""A Nuke Snake client, for user interaction to play the game.

Examples:
  # Connect to an available network server on localhost.
  %(prog)s
"""

import argparse
import curses
import locale
import random
import time

from common import game_pb2
import ai_player
import client_config
import common
import controller
import network


_MAX_LOCAL_PLAYERS = len(client_config.MOVE_KEYS)
assert _MAX_LOCAL_PLAYERS == len(client_config.ACTION_KEYS)


class Client(object):
  def __init__(self, game_server):
    self._game_server = game_server
    self._local_player_ids_ordered = []  # includes AIs
    self._ai_players_by_id = {}
    self._player_info_by_id = {}
    self._player_secret_by_id = {}

    self._window = None
    self._block_palettes_by_type = {}
    self._player_palettes = []
    self._num_message_lines = 1

    self._game_state = None

  def Register(self, name, ai=False):
    secret = str(random.random())
    player_id = self._game_server.Register(secret, name)
    info = game_pb2.PlayerInfo(player_id=player_id, name=name)
    self._player_secret_by_id[player_id] = secret
    self._local_player_ids_ordered.append(player_id)
    if ai:
      self._ai_players_by_id[player_id] = ai_player.Player(secret, info)
    self._player_info_by_id[player_id] = info

  def UnregisterAll(self):
    for secret in self._player_secret_by_id.values():
      self._game_server.Unregister(secret)

  @staticmethod
  def CursesWrappedLoop(window, client):
    client._CursesWrappedLoop(window)

  def _CursesWrappedLoop(self, window):
    self._SetUpCurses(window)
    self._num_message_lines += len(self._local_player_ids_ordered)

    while True:
      time.sleep(client_config.UPDATE_INTERVAL_SEC)

      key_code = window.getch()
      local_player_index = 0
      for player_id in self._local_player_ids_ordered:
        if player_id not in self._ai_players_by_id:
          info = self._player_info_by_id[player_id]
          secret = self._player_secret_by_id[player_id]
          self._DoPlayerCommand(local_player_index, secret, info, key_code)
          local_player_index += 1

      updated = self._UpdateGameState()
      if updated or (
          self._game_state and
          self._game_state.stage == game_pb2.Stage.COLLECT_PLAYERS):
        for ai_player in self._ai_players_by_id.itervalues():
          ai_player.UpdateAndDoCommands(self._game_state, self._game_server)
      if self._CheckWindowSize() and (updated or key_code == curses.KEY_RESIZE):
        self._Repaint()
      self._window.refresh()

  def _SetUpCurses(self, window):
    self._window = window
    curses.curs_set(False)
    self._window.nodelay(True)

    palette_id = 1
    for fg, block_types in client_config.BLOCK_FOREGROUNDS.iteritems():
      for block_type in block_types:
        self._block_palettes_by_type[block_type] = palette_id
      curses.init_pair(palette_id, fg, client_config.BG_COLOR)
      palette_id += 1
    for color in client_config.PLAYER_COLORS:
      curses.init_pair(palette_id, color, client_config.BG_COLOR)
      self._player_palettes.append(palette_id)
      palette_id += 1

  def _DoPlayerCommand(self, i, secret, info, key_code):
    x, y = client_config.MOVE_KEYS[i].get(key_code, (0, 0))
    if x or y:
      self._game_server.Move(secret, game_pb2.Coordinate(x=x, y=y))
    if key_code == client_config.ACTION_KEYS[i]:
      self._game_server.Action(secret)

  def _UpdateGameState(self):
    states = self._game_server.GetUpdates()
    if not states:
      return False
    self._game_state = states[-1]
    self._player_info_by_id = dict(
        (info.player_id, info) for info in self._game_state.player_info)
    return True

  def _CheckWindowSize(self):
    h, w = self._window.getmaxyx()
    if (self._game_state and
        self._game_state.size.x < w and
        self._game_state.size.y + self._num_message_lines <= h):
      return True

    if self._game_state:
      message = (
          'Resize to %dx%d (now %dx%d).' %
          (self._game_state.size.x + 1,
           self._game_state.size.y + self._num_message_lines,
           w,
           h))
    else:
      message = 'Waiting for initial server data...'

    self._window.erase()
    self._window.addstr(h / 2, w / 2 - len(message) / 2, message)

    return False

  def _Repaint(self):
    h, w = self._window.getmaxyx()

    self._window.erase()

    for block in self._game_state.block:
      self._RenderBlock(block)

    for i, player_id in enumerate(self._local_player_ids_ordered, 1):
      self._RenderSummaryLine(i, player_id, h, w)

    message = ''
    if self._game_state.stage == game_pb2.Stage.COLLECT_PLAYERS:
      message = 'Press action to start round %d.' % self._game_state.round_num
    else:
      for local_info in self._player_info_by_id.values():
        if local_info.alive == game_pb2.PlayerInfo.DEAD:
          message += (
              '%s Dies (score %d) ' %
              (local_info.name, local_info.score))
    if self._game_state.stage == game_pb2.Stage.GAME_OVER:
      message = 'Game Over!'
      for info in self._game_state.player_info:
        message += ' %s: %d' % (info.name, info.score)
    elif self._game_state.stage == game_pb2.Stage.ROUND_END:
      living_info = None
      for info in self._game_state.player_info:
        if info.alive == game_pb2.PlayerInfo.ALIVE:
          living_info = info
          break
      if living_info:
        message = (
            '%s wins! (score %d) %s' %
            (living_info.name, living_info.score, message))
    if self._game_state.HasField('lives'):
      # hearts for lives
      message = '%s %s' % (u'\u2665' * self._game_state.lives, message)
    self._window.addstr(h - 1, 1, message.encode('utf-8'))

  def _RenderSummaryLine(self, local_player_cardinal, player_id, h, w):
    info = self._player_info_by_id[player_id]
    player_icon = client_config.PLAYER_ICONS[
        info.player_id % len(client_config.PLAYER_ICONS)]
    intro = '%4d %s %s' % (info.score, player_icon, info.name)
    palette_attr = curses.color_pair(
        self._player_palettes[info.player_id % len(self._player_palettes)])
    self._window.addstr(
        h - (1 + local_player_cardinal), 0, intro.encode('utf-8'), palette_attr)
    power_ups = ''.join(
        client_config.BLOCK_CHARACTERS[p.type]
        for p in info.power_up)
    if power_ups:
      self._window.addstr(
          ('  ' + power_ups).encode('utf-8'), palette_attr + curses.A_BLINK)
    inventory = ''.join(
        client_config.BLOCK_CHARACTERS[t] for t in info.inventory)
    if inventory:
      self._window.addstr('  ' + inventory.encode('utf-8'), palette_attr)

  def _RenderBlock(self, block):
    s = '?'
    name = None
    s_attr = curses.A_NORMAL
    if block.type in (
        game_pb2.Block.PLAYER_HEAD, game_pb2.Block.PLAYER_TAIL):
      palette_id = self._player_palettes[
          block.player_id % len(self._player_palettes)]
    else:
      palette_id = self._block_palettes_by_type.get(block.type)
    if palette_id:
      s_attr += curses.color_pair(palette_id)
    if block.type == game_pb2.Block.PLAYER_HEAD:
      s = client_config.PLAYER_ICONS[
          block.player_id % len(client_config.PLAYER_ICONS)]
      info = self._player_info_by_id[block.player_id]
      if info.first_active_tick > self._game_state.tick:
        if (block.player_id in self._local_player_ids_ordered
            and block.player_id not in self._ai_players_by_id):
          s_attr += curses.A_BLINK
        if self._game_state.stage == game_pb2.Stage.COLLECT_PLAYERS:
          name = self._player_info_by_id[block.player_id].name
    else:
      s = client_config.BLOCK_CHARACTERS.get(
          block.type, client_config.DEFAULT_BLOCK_CHARACTER)
    self._window.addstr(block.pos.y, block.pos.x, s.encode('utf-8'), s_attr)
    if name is not None:
      name_x = block.pos.x + 2
      if name_x + len(name) >= self._game_state.size.x:
        name_x = block.pos.x - (2 + len(name))
      self._window.addstr(block.pos.y, name_x, name, s_attr)


def _PrintBlockSummary():
  print 'Blocks of the World (icons defined in client_config):'
  longest_name = max(map(len, game_pb2.Block.Type.keys()))
  row_t = '%{0}s  %s  %s'.format(longest_name)
  for block_type in game_pb2.Block.Type.values():
    description = client_config.BLOCK_DESCRIPTIONS.get(block_type)
    if description is not None:
      print (
          row_t %
          (game_pb2.Block.Type.Name(block_type).replace('_', ' ').capitalize(),
           client_config.BLOCK_CHARACTERS.get(block_type, '?'),
           description))


def RunClient(host, ai_names, server=None):
  game_server = server or network.Client(host, network.PORT)

  locale.setlocale(locale.LC_ALL, '')

  _PrintBlockSummary()

  client = Client(game_server)
  names = []
  while len(names) < _MAX_LOCAL_PLAYERS:
    i = len(names)
    print (
        'Player %d action key is %r, move keys are '
        % (i + 1, chr(client_config.ACTION_KEYS[i]))),
    move_keys = client_config.MOVE_KEYS[i].items()
    move_keys.sort(
        key=lambda key_and_coord: (key_and_coord[1][1], key_and_coord[1][0]))
    for c, _ in move_keys:
      print chr(c),
    print ''
    name = raw_input(
        'Name for player %d? [Just hit enter if you have everyone.] '
        % (i + 1)).strip()
    if not name:
      break
    names.append(name)
    client.Register(name)
  for ai_name in ai_names:
    client.Register(ai_name, ai=True)

  try:
    curses.wrapper(Client.CursesWrappedLoop, client)
  except KeyboardInterrupt:
    print 'Quitting.'
  finally:
    client.UnregisterAll()


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

  RunClient(args.host, args.ai, server=game_server)
