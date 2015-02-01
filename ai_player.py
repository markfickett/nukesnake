"""Computer-controlled snake."""


import logging
import random
import time

from common import ai_player_pb2, game_pb2
import common
import config


_DESIRABLE_BLOCKS = frozenset((
    game_pb2.Block.AMMO,
    game_pb2.Block.STAY_STILL,
    game_pb2.Block.FAST,
    game_pb2.Block.NUKE,
))
_ROUND_START_DELAY = 5.0


class Player(object):
  def __init__(self, secret, player_info):
    self._secret = secret
    self._info = player_info
    self._round_start_time = None

    self._SetAbilities(0)

  def _SetAbilities(self, round_num):

    if round_num >= 13:
      self._view_dist = 3
    elif round_num >= 10:
      self._pick_desirable_blocks = True
    elif round_num >= 7:
      self._view_dist = 2
      self._shooting = ai_player_pb2.Shoot.WHEN_CORNERED
    elif round_num >= 5:
      self._shooting = ai_player_pb2.Shoot.IMMEDIATE
    elif round_num >= 3:
      self._diagonals = True
    else:
      self._view_dist = 1
      self._shooting = ai_player_pb2.Shoot.NEVER
      self._diagonals = False
      self._pick_desirable_blocks = False

  def _MaybeStartRound(self, game_state, game_server):
    if game_state.stage == game_pb2.Stage.COLLECT_PLAYERS:
      if self._round_start_time is None:
        self._round_start_time = time.time()
      elif time.time() - self._round_start_time > _ROUND_START_DELAY:
        game_server.Action(self._secret)
    else:
      self._round_start_time = None

  def UpdateAndDoCommands(self, new_game_state, game_server):
    if new_game_state.stage != game_pb2.Stage.ROUND:
      self._SetAbilities(new_game_state.round_num)
      self._MaybeStartRound(new_game_state, game_server)
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
      logging.warning(
          'AI could not find its own head.\n%s\n%s',
          self._info,
          [str(b).replace('\n', ' ') for b in new_game_state.block
           if b.type == game_pb2.Block.PLAYER_HEAD])
      return
    default_dir = (player_head.direction.x, player_head.direction.y)

    nearby = []
    for dx in xrange(-self._view_dist, self._view_dist + 1):
      row = []
      for dy in xrange(-self._view_dist, self._view_dist + 1):
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
        if not self._diagonals and (i != 0 and j != 0):
          continue
        clear_in_view = True
        for dist in range(1, self._view_dist + 1):
          block = nearby[self._view_dist + i * dist][self._view_dist + j * dist]
          if block is None:
            if dist == 1:
              safe_directions.add((i, j))
          elif (block.type in _DESIRABLE_BLOCKS or
               (block.type == game_pb2.Block.ROCKET and
                block.direction.x == i and block.direction.y == j)):
            if self._pick_desirable_blocks:
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

    if self._shooting == ai_player_pb2.Shoot.NEVER:
      shoot = False
    elif self._shooting == ai_player_pb2.Shoot.IMMEDIATE:
      shoot = True
    if shoot and (config.INFINITE_AMMO or self._info.inventory):
      game_server.Action(self._secret)
