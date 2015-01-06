# http://pythonhosted.org/Pyro4/intro.html#simple-example

import random
import time

import Pyro4

import common
import messages_pb2


if __name__ == '__main__':
  secret = str(random.random())
  common.RegisterProtoSerialization()
  s = Pyro4.Proxy('PYRONAME:%s' % common.SERVER_URI_NAME)

  name = raw_input('What is your name? ').strip()

  s.Register(messages_pb2.RegisterRequest(
      player_secret=secret, player_name=name))

  try:
    while True:
      time.sleep(0.1)
      if random.random() > 0.9:
        move = messages_pb2.Coordinate(
            x=random.randint(-1, 1),
            y=random.randint(-1, 1))
        s.Move(messages_pb2.MoveRequest(
            player_secret=secret,
            move=move))
      state = s.GetGameState()
      for player in state.player:
        print '%s:\t%d\t%d\t' % (player.name, player.pos.x, player.pos.y),
      print ''
  except KeyboardInterrupt:
    pass
