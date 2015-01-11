# http://pythonhosted.org/Pyro4/intro.html#simple-example

import curses
import locale
import random
import time

import Pyro4

import common
import messages_pb2


_UPDATE_INTERVAL = 1.0 / 120.0
_PLAYER_ICONS = [
    u'\N{UMBRELLA}',
    '$',
    u'\N{Circled Dot Operator}',
    u'\N{Ohm Sign}',
]
_PLAYER_ICONS += [chr(c) for c in range(ord('A'), ord('Z') + 1)]


def _DrawingMain(window, player_id, player_name):
  curses.curs_set(False)
  window.nodelay(True)
  last_state_hash = None

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

    state_req = messages_pb2.GetGameStateRequest()
    if last_state_hash is not None:
      state_req.hash = last_state_hash
    state = s.GetGameState(state_req)
    if not state:
      continue
    last_state_hash = state.hash

    if (state.stage == messages_pb2.GameState.COLLECT_PLAYERS
        and move_key == ord(' ')):
      s.Start()

    h, w = window.getmaxyx()
    if state.size.x >= w or state.size.y >= h:
      window.erase()
      _RenderMessage(
          window,
          'Resize to %dx%d (now %dx%d).'
          % (state.size.x + 1, state.size.y + 1, w, h))
      window.refresh()
      continue

    alive = False
    winner_name = None
    for info in state.player_info:
      if info.player_id == player_id:
        alive = info.alive
      if info.alive:
        winner_name = info.name

    window.erase()
    for block in state.block:
      _RenderBlock(block, window, player_id, state.stage)
    if state.stage == messages_pb2.GameState.COLLECT_PLAYERS:
      _RenderMessage(window, 'Press space to start.')
    elif state.stage == messages_pb2.GameState.ROUND_START:
      _RenderMessage(window, 'Ready...')
    elif not alive:
      _RenderMessage(window, '%s Dies' % player_name)
    if state.stage == messages_pb2.GameState.ROUND_END and winner_name:
      _RenderMessage(window, '%s wins!' % winner_name, y_offset=1)
    window.refresh()


def _RenderMessage(window, msg, y_offset=0):
  h, w = window.getmaxyx()
  window.addstr(h / 2 + y_offset, w / 2 - len(msg) / 2, msg)


def _RenderBlock(block, window, player_id, stage):
  B = messages_pb2.Block
  s = '?'
  s_attr = curses.A_NORMAL
  if block.type == B.PLAYER_HEAD:
    s = _PLAYER_ICONS[block.player_id % len(_PLAYER_ICONS)]
    if stage != messages_pb2.GameState.ROUND and block.player_id == player_id:
      s_attr = curses.A_BLINK
  else:
    # http://www.alanflavell.org.uk/unicode/unidata25.html
    s = {
      B.PLAYER_TAIL: u'\N{DARK SHADE}',
      B.WALL: u'\N{FULL BLOCK}',
      B.MINE: u'\N{REFERENCE MARK}',
    }.get(block.type, '?')
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
    s.Unregister(messages_pb2.UnregisterRequest(player_secret=secret))
