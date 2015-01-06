# http://pythonhosted.org/Pyro4/intro.html#simple-example

import curses
import locale
import random
import time

import Pyro4

import common
import messages_pb2


_UPDATE_INTERVAL = 0.1
_PLAYER_ICONS = (
    u'\u2603',  # snowman
    u'\u2602',  # umbrella
    u'\u2600',  # sun
)


def _DrawingMain(window):
  player_icons = {}
  curses.curs_set(False)
  window.nodelay(True)

  while True:
    time.sleep(_UPDATE_INTERVAL)

    move_key = window.getch()
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
    state = s.GetGameState()

    h, w = window.getmaxyx()
    if w > state.size.x or h > state.size.y:
      raise RuntimeError(
          'World %s too big for window w=%d h=%d.'
          % (state.size, w, h))

    window.erase()
    for player in state.player:
      icon = player_icons.get(player.name)
      if not icon:
        icon = random.choice(_PLAYER_ICONS)
        player_icons[player.name] = icon
      window.addstr(player.pos.y, player.pos.x, icon.encode('utf-8'))
    window.refresh()


if __name__ == '__main__':
  secret = str(random.random())
  common.RegisterProtoSerialization()
  s = Pyro4.Proxy('PYRONAME:%s' % common.SERVER_URI_NAME)

  name = raw_input('What is your name? ').strip()

  s.Register(messages_pb2.RegisterRequest(
      player_secret=secret, player_name=name))

  locale.setlocale(locale.LC_ALL, '')

  try:
    curses.wrapper(_DrawingMain)
  finally:
    s.Unregister(messages_pb2.UnregisterRequest(player_secret=secret))
