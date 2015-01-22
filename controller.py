"""Controller of game state and client interaction; the central game logic."""

import argparse
import collections
import itertools
import random
import time

import common
import config
import height_map
import game_pb2  # protoc --python_out=. *.proto
import network_pb2


UPDATE_INTERVAL = max(0.05, config.SPEED)
_PAUSE_TICKS = 2 / UPDATE_INTERVAL

_STARTING_TAIL_LENGTH = max(0, config.STARTING_TAIL_LENGTH)
_MAX_ROCKET_AGE = 300
_ROCKETS_PER_AMMO = 3
_AMMO_RARITY = max(1, config.AMMO_RARITY)
_MINE_RARITY = max(2, config.MINE_RARITY)
_HEAD_MOVE_INTERVAL = 3  # This makes rockets faster than player snakes.

_B = game_pb2.Block


class Controller(object):
  def __init__(self, width, height):
    self._size = game_pb2.Coordinate(
        x=max(4, width),
        y=max(4, height))

    self._player_heads_by_secret = {}
    self._next_player_id = 0
    self._player_infos_by_secret = {}

    self._dirty = True
    self._state_hash = 0
    self._stage = None
    self._start_requested = False
    self._last_update = time.time()
    self._tick = 0
    self._round_num = 0

    self._SetStage(game_pb2.Stage.COLLECT_PLAYERS)

  def _SetStage(self, stage):
    if self._stage == stage:
      return
    self._stage = stage
    self._pause_ticks = 0
    self._dirty = True
    self._start_requested = False

    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      # When preparing for a new round to start, reinitialize state and
      # reset all players to alive.
      self._rockets = []
      # a subset of static blocks; to track expiration
      self._player_tails_by_id = collections.defaultdict(lambda: list())

      # If (almost) everyone left, reset more things.
      reset_stats = False
      if len(self._player_infos_by_secret) <= 1:
        self._round_num = 0
        reset_stats = True
      else:
        self._round_num += 1

      self._BuildStaticBlocks()
      for secret, info in self._player_infos_by_secret.iteritems():
        self._AddPlayerHeadResetPos(secret, info)
        info.alive = True
        if reset_stats:
          info.score = 0
          del info.inventory[:]

  def GetGameState(self, last_hash):
    if self._dirty:
      environment_blocks = []
      if self._stage != game_pb2.Stage.COLLECT_PLAYERS:
        for row in self._static_blocks_grid:
          environment_blocks += filter(bool, row)
        environment_blocks += self._rockets
      self._client_facing_state = network_pb2.Response(
          size=self._size,
          player_info=self._player_infos_by_secret.values(),
          block=environment_blocks + self._player_heads_by_secret.values(),
          stage=self._stage,
          round_num=self._round_num)
      self._dirty = False
      self._state_hash += 1

    return (self._state_hash, None) if last_hash == self._state_hash else (
        self._state_hash, self._client_facing_state)

  def Register(self, secret, name):
    if secret in self._player_infos_by_secret:
      raise RuntimeError(
          'Player %s already registered as %s.' % (
              secret,
              self._player_infos_by_secret[secret]))
    if not name:
      raise RuntimeError('Player name %r not allowed!' % name)
    if name in [
        info.name for info in self._player_infos_by_secret.values()]:
      raise RuntimeError('Player name %s is already taken.' % name)

    info = game_pb2.PlayerInfo(
        player_id=self._next_player_id,
        name=name,
        alive=self._stage == game_pb2.Stage.COLLECT_PLAYERS,
        score=0)
    self._player_infos_by_secret[secret] = info
    self._next_player_id += 1
    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      self._AddPlayerHeadResetPos(secret, info)
    return info.player_id

  def _AddPlayerHeadResetPos(self, player_secret, player_info):
    head = self._player_heads_by_secret.get(player_secret)

    tries = 0
    collides = True
    while collides and tries < 10:
      starting_pos = _RandomPosWithin(self._size)
      collides = False
      tries += 1
      for dx in xrange(-1, 2):
        for dy in xrange(-1, 2):
          hit = self._static_blocks_grid[
              (starting_pos.x + dx) % self._size.x][
              (starting_pos.y + dy) % self._size.y]
          if hit is not None:
            collides = True
            print (
                '%s was going to start on a %s, retrying.' %
                (player_info.name, _B.Type.Name(hit.type).lower()))
            break

    if head:
      head.pos.MergeFrom(starting_pos)
    else:
      head = _B(
          type=_B.PLAYER_HEAD,
          pos=starting_pos,
          direction=game_pb2.Coordinate(x=1, y=0),
          player_id=player_info.player_id,
          created_tick=self._tick)
      self._player_heads_by_secret[player_secret] = head
    self._dirty = True

  def Unregister(self, secret):
    self._player_infos_by_secret.pop(secret, None)
    head = self._player_heads_by_secret.pop(secret, None)
    if head:
      self._KillPlayer(head.player_id)
      self._dirty = True

  def _BuildStaticBlocks(self):
    self._static_blocks_grid = common.MakeGrid(self._size)
    def _Block(block_type, x, y):
      return _B(
          type=block_type,
          pos=game_pb2.Coordinate(x=x, y=y))

    if config.TERRAIN:
      hm = height_map.MakeHeightMap(self._size.x, self._size.y, 0, 20)
      for i in xrange(self._size.x):
        for j in xrange(self._size.y):
          if hm[i][j] >= 13:
            self._static_blocks_grid[i][j] = _Block(_B.ROCK, i, j)
          elif hm[i][j] >= 12:
            self._static_blocks_grid[i][j] = _Block(_B.TREE, i, j)

    if config.WALLS:
      for x in range(0, self._size.x):
        for y in (0, self._size.y - 1):
          self._static_blocks_grid[x][y] = _Block(_B.WALL, x, y)
      for y in range(0, self._size.y):
        for x in (0, self._size.x - 1):
          self._static_blocks_grid[x][y] = _Block(_B.WALL, x, y)

    if not config.INFINITE_AMMO:
      for _ in xrange(self._size.x * self._size.y / _AMMO_RARITY):
        pos = _RandomPosWithin(self._size)
        self._static_blocks_grid[pos.x][pos.y] = _B(type=_B.AMMO, pos=pos)

    if config.MINES:
      if config.MINE_CLUSTERS:
        hm = height_map.MakeHeightMap(
            self._size.x, self._size.y, 0, 30, blur_size=4)
        for i in xrange(self._size.x):
          for j in xrange(self._size.y):
            if hm[i][j] >= 17 and self._static_blocks_grid[i][j] is None:
              self._static_blocks_grid[i][j] = _Block(_B.MINE, i, j)
      else:
        for _ in xrange(self._size.x * self._size.y / _MINE_RARITY):
          pos = _RandomPosWithin(self._size)
          self._static_blocks_grid[pos.x][pos.y] = _B(type=_B.MINE, pos=pos)

  def Move(self, secret, direction):
    if abs(direction.x) > 1 or abs(direction.y) > 1:
      raise RuntimeError('Illegal move %s with value > 1.' % direction)
    if not (direction.x or direction.y):
      raise RuntimeError('Cannot stand still.')
    player_head = self._player_heads_by_secret.get(secret)
    if player_head:
      player_head.direction.MergeFrom(direction)

  def Action(self, secret):
    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      if len(self._player_infos_by_secret) > 1:
        self._start_requested = True
    elif self._stage == game_pb2.Stage.ROUND:
      player_head = self._player_heads_by_secret.get(secret)
      if player_head:
        if config.INFINITE_AMMO:
          has_rocket = True
        else:
          info = self._player_infos_by_secret[secret]
          if info.inventory and info.inventory[-1] == _B.ROCKET:
            new_inventory = info.inventory[:-1]
            del info.inventory[:]
            info.inventory.extend(new_inventory)
            has_rocket = True
          else:
            has_rocket = False
        if has_rocket:
          self._AddRocket(
              player_head.pos, player_head.direction, player_head.player_id)

  def _AddRocket(self, origin, direction, player_id):
    rocket_pos = game_pb2.Coordinate(
        x=(origin.x + direction.x) % self._size.x,
        y=(origin.y + direction.y) % self._size.y)
    self._rockets.append(_B(
        type=_B.ROCKET,
        pos=rocket_pos,
        direction=direction,
        created_tick=self._tick,
        player_id=player_id))
    self._dirty = True

  def Update(self):
    t = time.time()
    dt = t - self._last_update
    if dt < UPDATE_INTERVAL:
      return False
    self._last_update = t

    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      if self._start_requested:
        self._SetStage(game_pb2.Stage.ROUND_START)
    elif self._stage == game_pb2.Stage.ROUND_START:
      if self._pause_ticks > _PAUSE_TICKS:
        self._SetStage(game_pb2.Stage.ROUND)
    elif self._stage == game_pb2.Stage.ROUND:
      self._Tick()
    elif self._stage == game_pb2.Stage.ROUND_END:
      if self._pause_ticks > _PAUSE_TICKS:
        self._SetStage(game_pb2.Stage.COLLECT_PLAYERS)
    self._tick += 1
    self._pause_ticks += 1
    return True

  def _Tick(self):
    if self._tick % _HEAD_MOVE_INTERVAL == 0:
      # Add new tail segments, move heads.
      for head in self._player_heads_by_secret.itervalues():
        tail = _B(
            type=_B.PLAYER_TAIL,
            pos=head.pos,
            created_tick=self._tick,
            player_id=head.player_id)
        self._player_tails_by_id[head.player_id].append(tail)
        self._static_blocks_grid[tail.pos.x][tail.pos.y] = tail
      for head in self._player_heads_by_secret.values():
        self._AdvanceBlock(head)

    for rocket in self._rockets:
      self._AdvanceBlock(rocket)

    # Expire tails.
    tail_expiry = _HEAD_MOVE_INTERVAL * (
        _STARTING_TAIL_LENGTH + self._tick / 50)
    for tails in self._player_tails_by_id.values():
      while tails and (self._tick - tails[0].created_tick >= tail_expiry):
        self._static_blocks_grid[tails[0].pos.x][tails[0].pos.y] = None
        tails.pop(0)

    # Expire rockets.
    rm_indices = []
    for i, rocket in enumerate(self._rockets):
      if self._tick - rocket.created_tick >= _MAX_ROCKET_AGE:
        rm_indices.append(i)
    for i in reversed(rm_indices):
      del self._rockets[i]

    self._ProcessCollisions()

    if len(filter(
        lambda p: p.alive, self._player_infos_by_secret.values())) <= 1:
      self._SetStage(game_pb2.Stage.ROUND_END)

    self._dirty = True

  def _AdvanceBlock(self, block):
    block.pos.x = (block.pos.x + block.direction.x) % self._size.x
    block.pos.y = (block.pos.y + block.direction.y) % self._size.y

  def _ProcessCollisions(self):
    destroyed = []
    moving_blocks_grid = common.MakeGrid(self._size)
    for b in itertools.chain(
        self._player_heads_by_secret.values(), self._rockets):
      hit = None
      for target_grid in (moving_blocks_grid, self._static_blocks_grid):
        hit = target_grid[b.pos.x][b.pos.y]
        if hit:
          destroyed.append(hit)
          if not self._CheckIsPlayerHeadAddAmmo(b, hit):
            destroyed.append(b)
      if not hit:
        moving_blocks_grid[b.pos.x][b.pos.y] = b
    for b in destroyed:
      if b.type == _B.PLAYER_HEAD:
        self._KillPlayer(b.player_id)
      elif b.type == _B.ROCKET:
        if b in self._rockets:  # for rocket-rocket collision
          self._rockets.remove(b)
      elif self._static_blocks_grid[b.pos.x][b.pos.y] is b:
        self._static_blocks_grid[b.pos.x][b.pos.y] = None
        if b.type == _B.PLAYER_TAIL:
          tails = self._player_tails_by_id[b.player_id]
          # If two players die at once, tails might already be removed.
          if b in tails:
            tails.remove(b)
        elif b.type == _B.MINE:
          for i in range(-1, 2):
            for j in range(-1, 2):
              if i == 0 and j == 0:
                continue
              self._AddRocket(
                  b.pos, game_pb2.Coordinate(x=i, y=j), b.player_id)

  def _CheckIsPlayerHeadAddAmmo(self, head, ammo):
    if not (
        not config.INFINITE_AMMO and
        head.type == _B.PLAYER_HEAD and ammo.type == _B.AMMO):
      return False
    info = None
    for player in self._player_infos_by_secret.values():
      if head.player_id == player.player_id:
        info = player
        break
    if info:
      info.inventory.extend([_B.ROCKET] * _ROCKETS_PER_AMMO)
      return True
    return False

  def _KillPlayer(self, player_id):
    secret = None
    for secret, head in self._player_heads_by_secret.iteritems():
      if head.player_id == player_id:
        break
    if secret:
      del self._player_heads_by_secret[secret]
    # Tail blocks will no longer update, but are already in statics.
    self._player_tails_by_id.pop(player_id, None)
    for other_secret, info in self._player_infos_by_secret.iteritems():
      if secret == other_secret:
        # If this is after Unregister, there may be no PlayerInfo for the
        # player being killed.
        info.alive = False
      elif info.alive:
        info.score += 1


def _RandomPosWithin(world_size):
  return game_pb2.Coordinate(
      x=random.randint(1, world_size.x - 2),
      y=random.randint(1, world_size.y - 2))


def AddControllerArgs(parser):
  parser.add_argument(
      '-x', '--width', type=int, default=79,
      help=(
          'Width of the world in blocks (characters). Network clients pick '
          'up the size of the world from the server; standalone clients '
          'specify their own world size.'))
  parser.add_argument(
      '-y', '--height', type=int, default=23,
      help='Height of the world in blocks.')
