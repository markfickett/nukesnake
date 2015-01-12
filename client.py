# http://pythonhosted.org/Pyro4/intro.html#simple-example

import curses
import locale
import random
import time

import Pyro4

import common
import messages_pb2


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


def _DrawingMain(window, player_id, player_name):
  curses.curs_set(False)
  window.nodelay(True)
  last_state_hash = None

  block_palettes = {}
  palette_id = 1
  for fg, block_types in _BLOCK_FOREGROUNDS.iteritems():
    for block_type in block_types:
      block_palettes[block_type] = palette_id
    curses.init_pair(palette_id, fg, _BG_COLOR)
    palette_id += 1
  player_palettes = []
  for color in _PLAYER_COLORS:
    curses.init_pair(palette_id, color, _BG_COLOR)
    player_palettes.append(palette_id)
    palette_id += 1

  while True:
    time.sleep(_UPDATE_INTERVAL)

    move_key = window.getch()
    curses.flushinp()
    x, y = {
        ord('q'): (-1, -1),
        ord('w'): (0, -1),
        ord('e'): (1, -1),
        ord('a'): (-1, 0),
        ord('s'): (0, 1),
        ord('d'): (1, 0),
        ord('z'): (-1, 1),
        ord('x'): (0, 1),
        ord('c'): (1, 1),
    }.get(move_key, (0, 0))
    if x or y:
      s.Move(messages_pb2.MoveRequest(
          player_secret=secret,
          move=messages_pb2.Coordinate(x=x, y=y)))
    if move_key == ord(' '):
      s.Action(messages_pb2.IdentifiedRequest(player_secret=secret))

    state_req = messages_pb2.GetGameStateRequest()
    if last_state_hash is not None:
      state_req.hash = last_state_hash
    state = s.GetGameState(state_req)
    if not state:
      continue
    last_state_hash = state.hash

    h, w = window.getmaxyx()
    if state.size.x >= w or state.size.y >= h:
      window.erase()
      _RenderMessage(
          window,
          'Resize to %dx%d (now %dx%d).'
          % (state.size.x + 1, state.size.y + 1, w, h))
      window.refresh()
      continue

    self_info = None
    living_info = None
    for info in state.player_info:
      if info.player_id == player_id:
        self_info = info
      if info.alive:
        living_info = info

    window.erase()
    for block in state.block:
      _RenderBlock(
          block,
          window,
          player_id,
          state.stage,
          block_palettes,
          player_palettes)
    if state.stage == messages_pb2.GameState.COLLECT_PLAYERS:
      _RenderMessage(window, 'Press space to start.')
    elif state.stage == messages_pb2.GameState.ROUND_START:
      _RenderMessage(window, 'Ready...')
    elif not self_info.alive:
      _RenderMessage(
          window, '%s Dies (score %d)' % (self_info.name, self_info.score))
    if state.stage == messages_pb2.GameState.ROUND_END and living_info:
      _RenderMessage(
          window,
          '%s wins! (score %d)'
          % (living_info.name, living_info.score), y_offset=1)
    window.refresh()


def _RenderMessage(window, msg, y_offset=0):
  h, w = window.getmaxyx()
  window.addstr(h / 2 + y_offset, w / 2 - len(msg) / 2, msg)


def _RenderBlock(
    block,
    window,
    player_id,
    stage,
    block_palettes,
    player_palettes):
  s = '?'
  s_attr = curses.A_NORMAL
  if block.type in (_B.PLAYER_HEAD, _B.PLAYER_TAIL):
    palette_id = player_palettes[block.player_id % len(player_palettes)]
  else:
    palette_id = block_palettes.get(block.type)
  if palette_id:
    s_attr += curses.color_pair(palette_id)
  if block.type == _B.PLAYER_HEAD:
    s = _PLAYER_ICONS[block.player_id % len(_PLAYER_ICONS)]
    if stage != messages_pb2.GameState.ROUND and block.player_id == player_id:
      s_attr += curses.A_BLINK
  else:
    s = _BLOCK_CHARACTERS.get(block.type, _DEFAULT_BLOCK_CHARACTER)
  window.addstr(block.pos.y, block.pos.x, s.encode('utf-8'), s_attr)


if __name__ == '__main__':
  secret = str(random.random())
  common.RegisterProtoSerialization()
  s = Pyro4.Proxy('PYRONAME:%s' % common.SERVER_URI_NAME)

  name = raw_input('What is your name? ').strip()

  resp = s.Register(messages_pb2.RegisterRequest(
      player_secret=secret, player_name=name))
  player_id = resp.player.player_id

  locale.setlocale(locale.LC_ALL, '')

  try:
    curses.wrapper(_DrawingMain, player_id, name)
  finally:
    s.Unregister(messages_pb2.IdentifiedRequest(player_secret=secret))
