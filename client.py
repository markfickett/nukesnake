#!/usr/bin/env python
"""A Nuke Snake client, for user interaction to play the game.

Examples:
  # Connect to an available network server.
  %(prog)s
  # Run without a network server.
  %(prog)s --standalone -x 200 -y 50

The client can be standalone, or communicate to a networked server."""

import argparse
import curses
import locale
import random
import time

import ai_player
import client_config
import common
import messages_pb2
import server


_MAX_LOCAL_PLAYERS = len(client_config.MOVE_KEYS)
assert _MAX_LOCAL_PLAYERS == len(client_config.ACTION_KEYS)


class Client:
  def __init__(self, game_server, update_server):
    self._game_server = game_server
    self._update_server = update_server
    self._players_secret_and_info = []
    self._local_player_ids = set()
    self._ai_players_by_id = {}
    self._player_info_by_id = {}

    self._window = None
    self._block_palettes_by_type = {}
    self._player_palettes = []

    self._game_state = None

  def Register(self, name, ai=False):
    secret = str(random.random())
    resp = self._game_server.Register(messages_pb2.RegisterRequest(
        player_secret=secret, player_name=name))
    self._players_secret_and_info.append((secret, resp.player))
    self._local_player_ids.add(resp.player.player_id)
    if ai:
      self._ai_players_by_id[resp.player.player_id] = ai_player.Player(
          secret, resp.player)
    self._player_info_by_id[resp.player.player_id] = resp.player

  def UnregisterAll(self):
    for secret, _ in self._players_secret_and_info:
      self._game_server.Unregister(
          messages_pb2.IdentifiedRequest(player_secret=secret))
    self._players_secret_and_info = []
    self._local_player_ids = set()
    self._ai_players_by_id = {}
    self._player_info_by_id = {}

  @staticmethod
  def CursesWrappedLoop(window, client):
    client._CursesWrappedLoop(window)

  def _CursesWrappedLoop(self, window):
    self._SetUpCurses(window)

    while True:
      time.sleep(client_config.UPDATE_INTERVAL_SEC)

      key_code = window.getch()
      local_player_index = 0
      for secret, info in self._players_secret_and_info:
        if info.player_id not in self._ai_players_by_id:
          self._DoPlayerCommand(local_player_index, secret, info, key_code)
          local_player_index += 1
      if self._update_server:
        self._game_server.Update()

      if self._UpdateGameState():
        self._Repaint()
        for ai_player in self._ai_players_by_id.itervalues():
          ai_player.UpdateAndDoCommands(self._game_state, self._game_server)

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
      self._game_server.Move(messages_pb2.MoveRequest(
          player_secret=secret,
          move=messages_pb2.Coordinate(x=x, y=y)))
    if key_code == client_config.ACTION_KEYS[i]:
      self._game_server.Action(
          messages_pb2.IdentifiedRequest(player_secret=secret))

  def _UpdateGameState(self):
    state_req = messages_pb2.GetGameStateRequest()
    if self._game_state is not None:
      state_req.hash = self._game_state.hash
    state = self._game_server.GetGameState(state_req)
    if not state:
      return False
    self._game_state = state
    for info in self._game_state.player_info:
      if info.player_id in self._player_info_by_id:
        self._player_info_by_id[info.player_id].MergeFrom(info)
    return True

  def _Repaint(self):
    h, w = self._window.getmaxyx()
    if self._game_state.size.x >= w or self._game_state.size.y >= h:
      self._window.erase()
      self._RenderMessage(
          'Resize to %dx%d (now %dx%d).'
          % (self._game_state.size.x + 1, self._game_state.size.y + 1, w, h))
      self._window.refresh()
      return

    self._window.erase()
    for block in self._game_state.block:
      self._RenderBlock(block)
    if self._game_state.stage == messages_pb2.GameState.COLLECT_PLAYERS:
      self._RenderMessage('Press action to start.')
    elif self._game_state.stage == messages_pb2.GameState.ROUND_START:
      self._RenderMessage('Ready...')
    else:
      for i, (_, local_info) in enumerate(self._players_secret_and_info):
        if not local_info.alive:
          self._RenderMessage(
              '%s Dies (score %d)' % (local_info.name, local_info.score),
              y_offset=-(i + 1))
    if self._game_state.stage == messages_pb2.GameState.ROUND_END:
      living_info = None
      for info in self._game_state.player_info:
        if info.alive:
          living_info = info
          break
      if living_info:
        self._RenderMessage(
            '%s wins! (score %d)' % (living_info.name, living_info.score))
    self._window.refresh()

  def _RenderBlock(self, block):
    s = '?'
    name = None
    s_attr = curses.A_NORMAL
    if block.type in (
        messages_pb2.Block.PLAYER_HEAD, messages_pb2.Block.PLAYER_TAIL):
      palette_id = self._player_palettes[
          block.player_id % len(self._player_palettes)]
    else:
      palette_id = self._block_palettes_by_type.get(block.type)
    if palette_id:
      s_attr += curses.color_pair(palette_id)
    if block.type == messages_pb2.Block.PLAYER_HEAD:
      s = client_config.PLAYER_ICONS[
          block.player_id % len(client_config.PLAYER_ICONS)]
      if (self._game_state.stage != messages_pb2.GameState.ROUND
          and block.player_id in self._local_player_ids):
        if block.player_id not in self._ai_players_by_id:
          s_attr += curses.A_BLINK
        if self._game_state.stage == messages_pb2.GameState.COLLECT_PLAYERS:
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

  def _RenderMessage(self, msg, y_offset=0):
    h, w = self._window.getmaxyx()
    self._window.addstr(h / 2 + y_offset, w / 2 - len(msg) / 2, msg)


if __name__ == '__main__':
  summary_line, _, main_doc = __doc__.partition('\n\n')
  parser = argparse.ArgumentParser(
      description=summary_line,
      epilog=main_doc,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '-s', '--standalone', action='store_true',
      help='Run without a network server, all players on the same keyboard.')
  parser.add_argument(
      '-a', '--ai', action='append', default=[],
      help='Names for AI players to add to the game.')
  server.AddGameServerArgs(parser)
  args = parser.parse_args()

  if args.standalone:
    game_server = server.Server(args.width, args.height)
  else:
    import Pyro4
    common.RegisterProtoSerialization()
    game_server = Pyro4.Proxy('PYRONAME:%s' % common.SERVER_URI_NAME)

  locale.setlocale(locale.LC_ALL, '')

  client = Client(game_server, args.standalone)
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
    name = raw_input('Name for player %d? ' % (i + 1)).strip()
    if not name:
      break
    names.append(name)
    client.Register(name)
  for ai_name in args.ai:
    client.Register(ai_name, ai=True)

  try:
    curses.wrapper(Client.CursesWrappedLoop, client)
  except KeyboardInterrupt:
    print 'Quitting.'
  finally:
    client.UnregisterAll()
