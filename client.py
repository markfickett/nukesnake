# http://pythonhosted.org/Pyro4/intro.html#simple-example

import curses
import locale
import random
import time

import Pyro4

import config
import common
import messages_pb2
import server


_B = messages_pb2.Block
_UPDATE_INTERVAL = 1.0 / 120.0
# alanflavell.org.uk/unicode/unidata25.html and unicode-table.com/
_PLAYER_ICONS = [
    u'\N{UMBRELLA}',
    '$',
    u'\N{Circled Dot Operator}',
    u'\N{Ohm Sign}',
]
_PLAYER_ICONS += [chr(c) for c in range(ord('A'), ord('Z') + 1)]
_BLOCK_CHARACTERS = {
  _B.PLAYER_TAIL: u'\N{DARK SHADE}',
  _B.WALL: u'\N{FULL BLOCK}',
  _B.ROCKET: u'\N{WHITE STAR}',
  _B.AMMO: u'\N{Tamil Sign Visarga}',
  _B.MINE: u'\N{REFERENCE MARK}',
}
_DEFAULT_BLOCK_CHARACTER = '?'
_BLOCK_FOREGROUNDS = {
  curses.COLOR_GREEN: (_B.WALL,),
  curses.COLOR_MAGENTA: (_B.MINE, _B.ROCKET),
}
_BG_COLOR = curses.COLOR_BLACK
_PLAYER_COLORS = (
  curses.COLOR_CYAN,
  curses.COLOR_RED,
  curses.COLOR_YELLOW,
  curses.COLOR_WHITE,
)


_MOVE_KEYS = (
    {
       ord('q'): (-1, -1),
       ord('w'): (0, -1),
       ord('e'): (1, -1),
       ord('a'): (-1, 0),
       ord('s'): (0, 1),
       ord('d'): (1, 0),
       ord('z'): (-1, 1),
       ord('x'): (0, 1),
       ord('c'): (1, 1),
    },
    {
       ord('u'): (-1, -1),
       ord('i'): (0, -1),
       ord('o'): (1, -1),
       ord('j'): (-1, 0),
       ord('k'): (0, 1),
       ord('l'): (1, 0),
       ord('m'): (-1, 1),
       ord(','): (0, 1),
       ord('.'): (1, 1),
    },
)
_MAX_LOCAL_PLAYERS = len(_MOVE_KEYS)
_ACTION_KEYS = (
    ord('`'),
    ord('\\'),
)
assert _MAX_LOCAL_PLAYERS == len(_ACTION_KEYS)


class Client:
  def __init__(self, game_server):
    self._game_server = game_server
    self._players_secret_and_info = []
    self._local_player_ids = set()
    self._player_info_by_id = {}

    self._window = None
    self._block_palettes_by_type = {}
    self._player_palettes = []

    self._game_state = None

  def Register(self, name):
    secret = str(random.random())
    resp = self._game_server.Register(messages_pb2.RegisterRequest(
        player_secret=secret, player_name=name))
    self._players_secret_and_info.append((secret, resp.player))
    self._local_player_ids.add(resp.player.player_id)
    self._player_info_by_id[resp.player.player_id] = resp.player

  def UnregisterAll(self):
    for secret, _ in self._players_secret_and_info:
      self._game_server.Unregister(
          messages_pb2.IdentifiedRequest(player_secret=secret))
    self._players_secret_and_info = []
    self._local_player_ids = set()
    self._player_info_by_id = {}

  @staticmethod
  def CursesWrappedLoop(window, client):
    client._CursesWrappedLoop(window)

  def _CursesWrappedLoop(self, window):
    self._SetUpCurses(window)

    while True:
      time.sleep(_UPDATE_INTERVAL)

      key_code = window.getch()
      curses.flushinp()
      for i, (secret, info) in enumerate(self._players_secret_and_info):
        self._DoPlayerCommand(i, secret, info, key_code)
      if config.NO_NETWORK:
        self._game_server.Update()

      if self._UpdateGameState():
        self._Repaint()

  def _SetUpCurses(self, window):
    self._window = window
    curses.curs_set(False)
    self._window.nodelay(True)

    palette_id = 1
    for fg, block_types in _BLOCK_FOREGROUNDS.iteritems():
      for block_type in block_types:
        self._block_palettes_by_type[block_type] = palette_id
      curses.init_pair(palette_id, fg, _BG_COLOR)
      palette_id += 1
    for color in _PLAYER_COLORS:
      curses.init_pair(palette_id, color, _BG_COLOR)
      self._player_palettes.append(palette_id)
      palette_id += 1

  def _DoPlayerCommand(self, i, secret, info, key_code):
    x, y = _MOVE_KEYS[i].get(key_code, (0, 0))
    if x or y:
      self._game_server.Move(messages_pb2.MoveRequest(
          player_secret=secret,
          move=messages_pb2.Coordinate(x=x, y=y)))
    if key_code == _ACTION_KEYS[i]:
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
    s_attr = curses.A_NORMAL
    if block.type in (_B.PLAYER_HEAD, _B.PLAYER_TAIL):
      palette_id = self._player_palettes[
          block.player_id % len(self._player_palettes)]
    else:
      palette_id = self._block_palettes_by_type.get(block.type)
    if palette_id:
      s_attr += curses.color_pair(palette_id)
    if block.type == _B.PLAYER_HEAD:
      s = _PLAYER_ICONS[block.player_id % len(_PLAYER_ICONS)]
      if (self._game_state.stage != messages_pb2.GameState.ROUND
          and block.player_id in self._local_player_ids):
        s_attr += curses.A_BLINK
    else:
      s = _BLOCK_CHARACTERS.get(block.type, _DEFAULT_BLOCK_CHARACTER)
    self._window.addstr(block.pos.y, block.pos.x, s.encode('utf-8'), s_attr)


  def _RenderMessage(self, msg, y_offset=0):
    h, w = self._window.getmaxyx()
    self._window.addstr(h / 2 + y_offset, w / 2 - len(msg) / 2, msg)


def Main():
  if config.NO_NETWORK:
    game_server = server.Server()
  else:
    common.RegisterProtoSerialization()
    game_server = Pyro4.Proxy('PYRONAME:%s' % common.SERVER_URI_NAME)

  locale.setlocale(locale.LC_ALL, '')

  client = Client(game_server)
  names = []
  while len(names) < _MAX_LOCAL_PLAYERS:
    i = len(names)
    print (
        'Player %d action key is %r, move keys are '
        % (i + 1, chr(_ACTION_KEYS[i]))),
    move_keys = _MOVE_KEYS[i].items()
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

  try:
    curses.wrapper(Client.CursesWrappedLoop, client)
  finally:
    client.UnregisterAll()


if __name__ == '__main__':
  Main()
