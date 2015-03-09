"""Controller of game state and client interaction; the central game logic."""

import argparse
import collections
import itertools
import logging
import random
import time

from common import game_pb2, network_pb2
import common
import config
import height_map
import scoring



_STARTING_TAIL_LENGTH = max(0, config.STARTING_TAIL_LENGTH)
_TAIL_GROWTH_TICKS = 100
_ROCKET_DURATION_TICKS = 300
_ROCKETS_PER_AMMO = 3
_AMMO_RARITY = max(1, config.AMMO_RARITY)
_POWER_UP_RARITY = max(1, config.POWER_UP_RARITY)
_MINE_RARITY = max(2, config.MINE_RARITY)
_HEAD_MOVE_INTERVAL = 3  # This makes rockets faster than player snakes.
_MAX_POS_TRIES = 50
_POS_CLEARANCE = 2

_NUKE_PROPORTION = 0.1
_NUKE_SIZE = 5

_B = game_pb2.Block
_POWER_UPS = [
  _B.FAST,
  _B.STAY_STILL,
  _B.TELEPORT,
  _B.INVINCIBLE,
]


class Controller(object):
  def __init__(self, width, height, mode, starting_round=0):
    self._size = game_pb2.Coordinate(
        x=max(4, width),
        y=max(4, height))

    self._player_heads_by_secret = {}
    self._next_player_id = 0
    self._player_infos_by_secret = {}

    self._scoring = {
        game_pb2.Mode.BATTLE: scoring.Battle,
        game_pb2.Mode.CLEAR_MINES: scoring.ClearMines,
    }[mode]()

    self._dirty = True
    self._state_hash = 0
    self._stage = None
    self._start_requested = False
    self._last_update = time.time()
    self._tick = 0
    self._starting_round = max(0, int(starting_round))
    self._round_num = self._starting_round

    self._SetSpeeds()
    self._SetStage(game_pb2.Stage.COLLECT_PLAYERS)

  def _SetSpeeds(self):
    slowest = 0.2  # one tick every .2s
    fastest = 0.005
    # This is inverse acceleration: larger numbers mean it takes more rounds
    # to get to faster speeds.
    rate = 10.0
    self._update_interval = slowest / (self._round_num / rate + 1.0) + fastest
    self._power_up_duration = int(6 / self._update_interval)
    self._pause_duration_ticks = int(2 / self._update_interval)
    logging.debug(
      'Update interval %.2fs power-up %d ticks pause %d ticks.',
      self._update_interval,
      self._power_up_duration,
      self._pause_duration_ticks)

  def _SetStage(self, stage):
    if self._stage == stage:
      return
    prev_stage = self._stage
    self._stage = stage
    self._pause_ticks = 0
    self._dirty = True
    self._start_requested = False
    logging.debug('%s', game_pb2.Stage.Id.Name(self._stage))

    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      # When preparing for a new round to start, reinitialize state and
      # reset all players to alive.
      self._rockets = []
      # a subset of static blocks; to track expiration
      self._player_tails_by_id = collections.defaultdict(lambda: list())

      # If (almost) everyone left, or the game was over, reset more things.
      reset_stats = prev_stage == game_pb2.Stage.GAME_OVER
      if reset_stats or not self._scoring.CanStartRound():
        self._round_num = self._starting_round
        self._scoring.Reset()
        reset_stats = True
      else:
        self._round_num += 1
      self._SetSpeeds()

      self._BuildStaticBlocks()
      for secret, info in self._player_infos_by_secret.iteritems():
        self._AddPlayerHeadResetPos(secret, info)
        info.alive = game_pb2.PlayerInfo.ALIVE
        if reset_stats:
          del info.inventory[:]
          del info.power_up[:]

      def _GenerateAllBLocks():
        for row in self._static_blocks_grid:
          for block in row:
            if block:
              yield block

      self._scoring.TerrainChanged(_GenerateAllBLocks())

  def GetGameState(self, last_hash):
    if self._dirty:
      environment_blocks = []
      if self._stage != game_pb2.Stage.COLLECT_PLAYERS:
        for row in self._static_blocks_grid:
          environment_blocks += filter(bool, row)
        environment_blocks += self._rockets
      self._client_facing_state = network_pb2.Response(
          tick=self._tick,
          size=self._size,
          player_info=self._player_infos_by_secret.values(),
          block=environment_blocks + self._player_heads_by_secret.values(),
          stage=self._stage,
          round_num=self._round_num)
      if self._scoring.lives is not None:
        self._client_facing_state.lives = max(0, self._scoring.lives)
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

    starting_alive = (
        game_pb2.PlayerInfo.ALIVE
        if self._stage == game_pb2.Stage.COLLECT_PLAYERS
        else game_pb2.PlayerInfo.ZOMBIE_DEAD)
    info = game_pb2.PlayerInfo(
        player_id=self._next_player_id,
        name=name,
        alive=starting_alive)
    self._scoring.AddPlayer(info)
    self._player_infos_by_secret[secret] = info
    self._next_player_id += 1
    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      self._AddPlayerHeadResetPos(secret, info)
    return info.player_id

  def _GetStartingPos(self):
    tries = 0
    collides = True
    while collides and tries < _MAX_POS_TRIES:
      starting_pos = _RandomPosWithin(self._size)
      collides = False
      tries += 1
      for dx in xrange(-_POS_CLEARANCE, _POS_CLEARANCE + 1):
        for dy in xrange(-_POS_CLEARANCE, _POS_CLEARANCE + 1):
          hit = self._static_blocks_grid[
              (starting_pos.x + dx) % self._size.x][
              (starting_pos.y + dy) % self._size.y]
          if hit is not None:
            collides = True
            break
    if collides:
      logging.info(
          'Did not find a starting position with %d clearance after %d tries.',
          _POS_CLEARANCE, _MAX_POS_TRIES)
      self._static_blocks_grid[starting_pos.x][starting_pos.y] = None
    return starting_pos

  def _AddPlayerHeadResetPos(self, player_secret, player_info, as_mine_at=None):
    head = self._player_heads_by_secret.get(player_secret)
    starting_pos = self._GetStartingPos()

    if head and head.type != _B.MINE and not as_mine_at:
      head.pos.MergeFrom(starting_pos)
    else:
      head = _B(
          type=_B.PLAYER_HEAD,
          pos=starting_pos,
          direction=game_pb2.Coordinate(x=1, y=0),
          player_id=player_info.player_id)
      if as_mine_at:
        head.type = _B.MINE
        head.pos.MergeFrom(as_mine_at)
      if not config.AUTO_MOVE:
        head.move = False
      self._player_heads_by_secret[player_secret] = head
    self._dirty = True

  def Unregister(self, secret):
    self._player_infos_by_secret.pop(secret, None)
    head = self._player_heads_by_secret.pop(secret, None)
    if head:
      self._scoring.RemovePlayer(head.player_id)
      self._KillPlayer(head.player_id, force=True)
      self._dirty = True

  def _BuildStaticBlocks(self):
    self._static_blocks_grid = common.MakeGrid(self._size)
    def _Block(block_type, x, y):
      return _B(
          type=block_type,
          pos=game_pb2.Coordinate(x=x, y=y))

    if config.TERRAIN:
      ripple_total = random.randint(-1, 1)
      ripple_x = random.randint(-1, 2)
      ripple_y = ripple_total - ripple_x
      logging.debug(
          'Generating terrain with ripple (%d, %d).', ripple_x, ripple_y)
      hm = height_map.MakeHeightMap(
          self._size.x,
          self._size.y,
          0,
          18,
          blur_size=1,
          ripple_amt=(ripple_x, ripple_y))
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
        self._static_blocks_grid[pos.x][pos.y] = _B(
            type=_B.AMMO if random.random() > _NUKE_PROPORTION else _B.NUKE,
            pos=pos)

    if config.MINES:
      if config.MINE_CLUSTERS:
        hm = height_map.MakeHeightMap(
            self._size.x, self._size.y, 0, random.randint(28, 30), blur_size=4)
        for i in xrange(self._size.x):
          for j in xrange(self._size.y):
            if hm[i][j] >= 17 and self._static_blocks_grid[i][j] is None:
              self._static_blocks_grid[i][j] = _Block(_B.MINE, i, j)
      else:
        for _ in xrange(self._size.x * self._size.y / _MINE_RARITY):
          pos = _RandomPosWithin(self._size)
          self._static_blocks_grid[pos.x][pos.y] = _B(type=_B.MINE, pos=pos)

    if self._round_num in (2, 4) or self._round_num >= 6:
      power_up = random.choice(_POWER_UPS + [_B.NUKE])
      for _ in xrange(self._size.x * self._size.y / _POWER_UP_RARITY):
        pos = _RandomPosWithin(self._size)
        self._static_blocks_grid[pos.x][pos.y] = _B(type=power_up, pos=pos)

  def Move(self, secret, direction):
    if abs(direction.x) > 1 or abs(direction.y) > 1:
      raise RuntimeError('Illegal move %s with value > 1.' % direction)
    if not (direction.x or direction.y):
      raise RuntimeError('Cannot stand still.')
    player_head = self._player_heads_by_secret.get(secret)
    if player_head:
      player_head.direction.MergeFrom(direction)
      player_head.ClearField('move')
    else:
      info = self._player_infos_by_secret.get(secret)
      if info:
        logging.warning(
            'Move from player %d (%s) with no head.',
            info.player_id, info.name)
      else:
        logging.error('Move from non-registered secret %r.', secret)

  def Action(self, secret):
    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      if self._scoring.CanStartRound():
        self._start_requested = True
    elif self._stage == game_pb2.Stage.ROUND:
      player_head = self._player_heads_by_secret.get(secret)
      if player_head:
        info = self._player_infos_by_secret[secret]
        if info.first_active_tick > self._tick:
          return
        if info.alive != game_pb2.PlayerInfo.ALIVE:
          return
        used_item = None
        if info.power_up and info.power_up[0].type == _B.TELEPORT:
          player_head.pos.MergeFrom(self._GetStartingPos())
        elif info.inventory:
          used_item = info.inventory[0]
          new_inventory = info.inventory[1:]
          del info.inventory[:]
          info.inventory.extend(new_inventory)
        elif config.INFINITE_AMMO:
          used_item = _B.ROCKET

        self._scoring.ItemUsed(info.player_id, used_item)
        if used_item == _B.ROCKET:
          self._AddRocket(
              player_head.pos,
              player_head.direction,
              player_head.player_id,
              initial_advance=True)
        elif used_item == _B.NUKE:
          self._AddNuke(
              player_head.pos, player_head.direction, player_head.player_id)
        elif used_item in _POWER_UPS:
          pup_block = _B(
              type=used_item,
              pos=player_head.pos,
              last_viable_tick=self._tick + self._power_up_duration)
          if used_item == _B.STAY_STILL:
            for other_info in self._player_infos_by_secret.itervalues():
              if other_info.player_id != info.player_id:
                other_info.power_up.extend([pup_block])
          else:
            info.power_up.extend([pup_block])
          if used_item == _B.TELEPORT:
            player_head.pos.MergeFrom(self._GetStartingPos())

  def _AddRocket(self, origin, direction, player_id, initial_advance=False):
    if initial_advance:
      rocket_pos = game_pb2.Coordinate(
          x=(origin.x + direction.x) % self._size.x,
          y=(origin.y + direction.y) % self._size.y)
    else:
      rocket_pos = origin
    self._rockets.append(_B(
        type=_B.ROCKET,
        pos=rocket_pos,
        direction=direction,
        last_viable_tick=self._tick + _ROCKET_DURATION_TICKS,
        player_id=player_id))
    self._dirty = True

  def _AddNuke(self, origin, direction, player_id):
    for i in xrange(-_NUKE_SIZE, _NUKE_SIZE + 1):
      for j in xrange(-_NUKE_SIZE, _NUKE_SIZE + 1):
        if (i, j) == (0, 0) or abs(i) + abs(j) > 1.7 * _NUKE_SIZE:
          continue
        pos = game_pb2.Coordinate(
            x=(origin.x + i) % self._size.x,
            y=(origin.y + j) % self._size.y)
        self._rockets.append(_B(
            type=_B.ROCKET,
            pos=pos,
            direction=game_pb2.Coordinate(
                x=(-1 if i < 0 else 1) if abs(i) >= abs(j) else 0,
                y=(-1 if j < 0 else 1) if abs(j) >= abs(i) else 0),
            last_viable_tick=self._tick + _ROCKET_DURATION_TICKS,
            player_id=player_id))
    self._dirty = True

  def Update(self):
    t = time.time()
    dt = t - self._last_update
    if dt < self._update_interval:
      return False
    self._last_update = t

    if self._stage == game_pb2.Stage.COLLECT_PLAYERS:
      if self._start_requested:
        self._SetStage(game_pb2.Stage.ROUND)
    elif self._stage == game_pb2.Stage.ROUND:
      self._Tick()
    elif self._stage in (game_pb2.Stage.ROUND_END, game_pb2.Stage.GAME_OVER):
      if self._pause_ticks > self._pause_duration_ticks:
        self._SetStage(game_pb2.Stage.COLLECT_PLAYERS)
    if self._stage != game_pb2.Stage.ROUND:
      self._SetPlayerStartTicks()
    self._tick += 1
    self._pause_ticks += 1
    return True

  def _SetPlayerStartTicks(self):
    for info in self._player_infos_by_secret.itervalues():
      info.first_active_tick = self._tick + self._pause_duration_ticks

  def _Tick(self):
    tail_duration = _HEAD_MOVE_INTERVAL * (
        _STARTING_TAIL_LENGTH + self._tick / _TAIL_GROWTH_TICKS)
    for secret, head in self._player_heads_by_secret.iteritems():
      info = self._player_infos_by_secret[secret]
      power_up = info.power_up[0].type if info.power_up else None
      if ((power_up == _B.FAST
           or self._tick % _HEAD_MOVE_INTERVAL == 0)
          and power_up != _B.STAY_STILL
          and self._tick >= info.first_active_tick):
        if head.move:
          # Add new tail segments, move heads.
          if head.type == _B.PLAYER_HEAD:  # no tails for zombies
            tail = _B(
                type=_B.PLAYER_TAIL,
                pos=head.pos,
                last_viable_tick=self._tick + tail_duration,
                player_id=head.player_id)
            self._player_tails_by_id[head.player_id].append(tail)
            self._static_blocks_grid[tail.pos.x][tail.pos.y] = tail

          self._AdvanceBlock(head)
          if not config.AUTO_MOVE:
            head.move = False

    for rocket in self._rockets:
      self._AdvanceBlock(rocket)

    # Expire tails.
    for tails in self._player_tails_by_id.values():
      while tails and (tails[0].last_viable_tick < self._tick):
        self._static_blocks_grid[tails[0].pos.x][tails[0].pos.y] = None
        tails.pop(0)

    # Expire rockets.
    rm_indices = []
    for i, rocket in enumerate(self._rockets):
      if rocket.last_viable_tick < self._tick:
        rm_indices.append(i)
    for i in reversed(rm_indices):
      del self._rockets[i]

    # Expire the oldest power-up and activate the next one in the queue.
    for info in self._player_infos_by_secret.itervalues():
      if info.power_up:
        if info.power_up[0].last_viable_tick < self._tick:
          remaining = info.power_up[1:]
          del info.power_up[:]
          if remaining:
            remaining[0].last_viable_tick = self._tick + self._power_up_duration
            info.power_up.extend(remaining)

    old_positions = {
        secret: head.pos
        for secret, head in self._player_heads_by_secret.iteritems()}
    self._ProcessCollisions()
    for secret, info in self._player_infos_by_secret.iteritems():
      if info.alive == game_pb2.PlayerInfo.DEAD:
        if self._scoring.UseRespawn():
          self._AddPlayerHeadResetPos(secret, info)
          info.alive = game_pb2.PlayerInfo.ALIVE
        else:
          self._AddPlayerHeadResetPos(
              secret, info, as_mine_at=old_positions[secret])
          info.alive = game_pb2.PlayerInfo.ZOMBIE
        info.first_active_tick = self._tick + self._pause_duration_ticks

    if self._scoring.IsGameOver():
      self._SetStage(game_pb2.Stage.GAME_OVER)
    elif self._scoring.IsRoundEnd():
      self._SetStage(game_pb2.Stage.ROUND_END)

    self._dirty = True

  def _AdvanceBlock(self, block):
    block.pos.x = (block.pos.x + block.direction.x) % self._size.x
    block.pos.y = (block.pos.y + block.direction.y) % self._size.y

  def _ProcessCollisions(self):
    destroyed = []
    moving_blocks_grid = common.MakeGrid(self._size)
    active_heads = [
        head for secret, head in self._player_heads_by_secret.iteritems()
        if self._tick >= self._player_infos_by_secret[secret].first_active_tick]
    for b in itertools.chain(active_heads, self._rockets):
      hit = None
      for target_grid in (moving_blocks_grid, self._static_blocks_grid):
        hit = target_grid[b.pos.x][b.pos.y]
        if hit:
          destroyed.append((hit, b))
          if not self._CheckIsPlayerHeadPickUpItem(b, hit):
            destroyed.append((b, hit))
      if not hit:
        moving_blocks_grid[b.pos.x][b.pos.y] = b
    for b, hit_by in destroyed:
      if b.type in (_B.PLAYER_HEAD, _B.MINE) and b.HasField('player_id'):
        self._KillPlayer(b.player_id)
        if b.type == _B.MINE:
          self._ExplodeAsMine(b)
      elif b.type == _B.ROCKET:
        # Mark for immediate expiration rather than finding/deleting now.
        b.last_viable_tick = self._tick - 1
      elif self._static_blocks_grid[b.pos.x][b.pos.y] is b:
        self._static_blocks_grid[b.pos.x][b.pos.y] = None
        if b.type == _B.PLAYER_TAIL:
          b.last_viable_tick = self._tick - 1
        elif b.type == _B.ROCK:
          self._static_blocks_grid[b.pos.x][b.pos.y] = _B(
              type=_B.BROKEN_ROCK, pos=b.pos)
        elif b.type == _B.MINE or (
            b.type == _B.NUKE and hit_by.type == _B.ROCKET):
          self._ExplodeAsMine(b)
      self._scoring.ItemDestroyed(
          hit_by.player_id if hit_by.HasField('player_id') else None, b)

  def _ExplodeAsMine(self, b):
    for i in range(-1, 2):
      for j in range(-1, 2):
        if i == 0 and j == 0:
          continue
        self._AddRocket(
            b.pos, game_pb2.Coordinate(x=i, y=j), b.player_id)

  def _CheckIsPlayerHeadPickUpItem(self, head, block):
    if not head.type == _B.PLAYER_HEAD:
      return False
    for player in self._player_infos_by_secret.values():
      if head.player_id == player.player_id:
        info = player
        break
    if not info:
      return False
    if block.type == _B.AMMO:
      info.inventory.extend([_B.ROCKET] * _ROCKETS_PER_AMMO)
    elif block.type in _POWER_UPS or block.type == _B.NUKE:
      info.inventory.append(block.type)
    else:
      return False
    return True

  def _KillPlayer(self, player_id, force=False):
    secret = None
    for secret, head in self._player_heads_by_secret.iteritems():
      if head.player_id == player_id:
        break
    if secret:
      if not force:
        info = self._player_infos_by_secret[secret]
        if (info.power_up and info.power_up[0].type == _B.INVINCIBLE or
            info.first_active_tick > self._tick):
          return
      del self._player_heads_by_secret[secret]
    # Tail blocks will no longer update, but are already in statics.
    self._player_tails_by_id.pop(player_id, None)
    for other_secret, info in self._player_infos_by_secret.iteritems():
      if secret == other_secret:
        # If this is after Unregister, there may be no PlayerInfo for the
        # player being killed.
        info.alive = (
            game_pb2.PlayerInfo.DEAD if info.alive == game_pb2.PlayerInfo.ALIVE
            else game_pb2.PlayerInfo.ZOMBIE_DEAD)


def _RandomPosWithin(world_size):
  return game_pb2.Coordinate(
      x=random.randint(1, world_size.x - 2),
      y=random.randint(1, world_size.y - 2))


def AddControllerArgs(parser):
  parser.add_argument(
      '-x', '--width', type=int, default=100,
      help=(
          'Width of the world in blocks (characters). Network clients pick '
          'up the size of the world from the server; standalone clients '
          'specify their own world size.'))
  parser.add_argument(
      '-y', '--height', type=int, default=30,
      help='Height of the world in blocks.')
  parser.add_argument(
      '-r', '--starting-round', type=int, default=0, dest='round',
      help='Round number to start on, controlling available power-ups etc.')
  parser.add_argument(
      '-m', '--mode', type=game_pb2.Mode.Id.Value, default=game_pb2.Mode.BATTLE,
      help='Goals and scoring for the game, one of %s.' %
           ', '.join(game_pb2.Mode.Id.keys()))
