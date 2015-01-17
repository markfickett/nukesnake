"""Computer-controlled snake."""


import common
import messages_pb2
import random


_VIEW_DIST = 1
_DESIRABLE_BLOCKS = frozenset((
    messages_pb2.Block.AMMO,
))


class Player:
  def __init__(self, secret, player_info):
    self._secret = secret
    self._info = player_info

  def UpdateAndDoCommands(self, new_game_state, game_server):
    if new_game_state.stage != messages_pb2.GameState.ROUND:
      return

    for player_info in new_game_state.player_info:
      if player_info.player_id == self._info.player_id:
        self._info = player_info
        break

    player_head = None
    grid = common.MakeGrid(new_game_state.size)
    for block in new_game_state.block:
      grid[block.pos.x][block.pos.y] = block
      if block.player_id == self._info.player_id:
        player_head = block
    if not player_head:
      raise RuntimeError(
          'AI could not find its own head.\n%s\n%s' % (
              self._info,
              [str(b).replace('\n', ' ') for b in new_game_state.block
               if b.type == messages_pb2.Block.PLAYER_HEAD]))

    nearby = []
    for dx in xrange(-_VIEW_DIST, _VIEW_DIST + 1):
      row = []
      for dy in xrange(-_VIEW_DIST, _VIEW_DIST + 1):
        row.append(grid[
            (player_head.pos.x + dx) % new_game_state.size.x][
            (player_head.pos.y + dy) % new_game_state.size.y])
      nearby.append(row)

    safe_directions = set()
    for i in xrange(-1, 2):
      for j in xrange(-1, 2):
        block = nearby[_VIEW_DIST + i][_VIEW_DIST + j]
        if i == 0 and j == 0:
          continue
        if block is None or block.type in _DESIRABLE_BLOCKS:
          safe_directions.add((i, j))

    default_dir = (player_head.direction.x, player_head.direction.y)
    if safe_directions and (default_dir not in safe_directions):
      x, y = random.choice(list(safe_directions))
      game_server.Move(messages_pb2.MoveRequest(
          player_secret=self._secret,
          move=messages_pb2.Coordinate(x=x, y=y)))

    if self._info.inventory:
      game_server.Action(messages_pb2.IdentifiedRequest(
          player_secret=self._secret))
