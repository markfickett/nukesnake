"""Computer-controlled snake."""


import common
import config
import game_pb2
import random


_VIEW_DIST = 3
_DESIRABLE_BLOCKS = frozenset((
    game_pb2.Block.AMMO,
))


class Player(object):
  def __init__(self, secret, player_info):
    self._secret = secret
    self._info = player_info

  def UpdateAndDoCommands(self, new_game_state, game_server):
    if new_game_state.stage != game_pb2.Stage.ROUND:
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
               if b.type == game_pb2.Block.PLAYER_HEAD]))
    default_dir = (player_head.direction.x, player_head.direction.y)

    nearby = []
    for dx in xrange(-_VIEW_DIST, _VIEW_DIST + 1):
      row = []
      for dy in xrange(-_VIEW_DIST, _VIEW_DIST + 1):
        row.append(grid[
            (player_head.pos.x + dx) % new_game_state.size.x][
            (player_head.pos.y + dy) % new_game_state.size.y])
      nearby.append(row)

    preferred_directions = set()
    clear_directions = set()
    safe_directions = set()
    for i in xrange(-1, 2):
      for j in xrange(-1, 2):
        if i == 0 and j == 0:
          continue
        clear_in_view = True
        for dist in range(1, _VIEW_DIST + 1):
          block = nearby[_VIEW_DIST + i * dist][_VIEW_DIST + j * dist]
          if block is None:
            if dist == 1:
              safe_directions.add((i, j))
          elif (block.type in _DESIRABLE_BLOCKS or
              (block.type == game_pb2.Block.ROCKET and
               block.direction.x == i and block.direction.y == j)):
            preferred_directions.add((i, j))
          else:
            clear_in_view = False
            break
        if clear_in_view:
          clear_directions.add((i, j))
    preferred_directions.intersection_update(safe_directions)

    new_dir = default_dir
    shoot = not safe_directions
    for possible_directions, should_shoot in (
        (preferred_directions, False),
        (clear_directions, False),
        (safe_directions, True)):
      if possible_directions:
        if default_dir not in possible_directions:
          new_dir = random.choice(list(possible_directions))
        shoot = should_shoot
        break
    if new_dir != default_dir:
      game_server.Move(
          self._secret, game_pb2.Coordinate(x=new_dir[0], y=new_dir[1]))

    if (config.INFINITE_AMMO or self._info.inventory) and shoot:
      game_server.Action(self._secret)
