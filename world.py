import itertools
import logging
import random

from common import game_pb2
import common
import config
import height_map


# parameters for terrain generation
_AMMO_RARITY = max(1, config.AMMO_RARITY)
_POWER_UP_RARITY = max(1, config.POWER_UP_RARITY)
_MINE_RARITY = max(2, config.MINE_RARITY)
_NUKE_PROPORTION = 0.1
# parameters for random position finding
_MAX_POS_TRIES = 50
_POS_CLEARANCE = 2

_B = game_pb2.Block
def _Block(block_type, x, y):
  return _B(
      type=block_type,
      pos=game_pb2.Coordinate(x=x, y=y))


class World(object):
  """Blocks in the world and management for tracking diffs."""
  def __init__(self, width, height):
    # Readonly, but exposed for common use in controller.
    self.size = game_pb2.Coordinate(x=max(4, width), y=max(4, height))
    self._updates_grid = common.MakeGrid(self.size)
    self._dirty = True

    self._static_blocks_grid = common.MakeGrid(self.size)
    self._expiring_blocks_soonest_first = []  # player tails
    self._rockets = []
    self._player_heads_by_key = {}

  def GenerateAndClearUpdates(self):
    for moving in itertools.chain(
        self._player_heads_by_key.itervalues(), self._rockets):
      self._updates_grid[moving.pos.x][moving.pos.y] = moving
    for row in self._updates_grid:
      for block in row:
        if block:
          yield block
    self._updates_grid = common.MakeGrid(self.size)
    self._dirty = False

  @property
  def dirty(self):
    return self._dirty

  def _GetRandomPos(self):
    """Returns a random coordinate within the world (and not in the walls)."""
    return game_pb2.Coordinate(
      x=random.randint(1, self.size.x - 2),
      y=random.randint(1, self.size.y - 2))

  def GetRandomPosClearOfTerrain(self):
    tries = 0
    collides = True
    while collides and tries < _MAX_POS_TRIES:
      starting_pos = self._GetRandomPos()
      collides = False
      tries += 1
      for dx in xrange(-_POS_CLEARANCE, _POS_CLEARANCE + 1):
        for dy in xrange(-_POS_CLEARANCE, _POS_CLEARANCE + 1):
          hit = self._static_blocks_grid[
              (starting_pos.x + dx) % self.size.x][
              (starting_pos.y + dy) % self.size.y]
          if hit is not None:
            collides = True
            break
    if collides:
      logging.info(
          'Did not find a starting position with %d clearance after %d tries.',
          _POS_CLEARANCE, _MAX_POS_TRIES)
      self._static_blocks_grid[starting_pos.x][starting_pos.y] = None
    return starting_pos

  def IterAllTerrainBlocks(self):
    """Yields all terrain blocks, for scoring analysis."""
    for row in self._static_blocks_grid:
      for block in row:
        if block:
          yield block

  def ClearBlocksAndRebuildTerrain(self, power_up_type):
    self._static_blocks_grid = common.MakeGrid(self.size)
    self._rockets = []

    if config.TERRAIN:
      ripple_total = random.randint(-1, 1)
      ripple_x = random.randint(-1, 2)
      ripple_y = ripple_total - ripple_x
      logging.debug(
          'Generating terrain with ripple (%d, %d).', ripple_x, ripple_y)
      hm = height_map.MakeHeightMap(
          self.size.x,
          self.size.y,
          0,
          18,
          blur_size=1,
          ripple_amt=(ripple_x, ripple_y))
      for i in xrange(self.size.x):
        for j in xrange(self.size.y):
          if hm[i][j] >= 13:
            self._static_blocks_grid[i][j] = _Block(_B.ROCK, i, j)
          elif hm[i][j] >= 12:
            self._static_blocks_grid[i][j] = _Block(_B.TREE, i, j)

    if config.WALLS:
      for x in range(0, self.size.x):
        for y in (0, self.size.y - 1):
          self._static_blocks_grid[x][y] = _Block(_B.WALL, x, y)
      for y in range(0, self.size.y):
        for x in (0, self.size.x - 1):
          self._static_blocks_grid[x][y] = _Block(_B.WALL, x, y)

    if not config.INFINITE_AMMO:
      for _ in xrange(self.size.x * self.size.y / _AMMO_RARITY):
        pos = self._GetRandomPos()
        self._static_blocks_grid[pos.x][pos.y] = _B(
            type=_B.AMMO if random.random() > _NUKE_PROPORTION else _B.NUKE,
            pos=pos)

    if config.MINES:
      if config.MINE_CLUSTERS:
        hm = height_map.MakeHeightMap(
            self.size.x,
            self.size.y,
            0,
            random.randint(28, 30),
            blur_size=4)
        for i in xrange(self.size.x):
          for j in xrange(self.size.y):
            if hm[i][j] >= 17 and self._static_blocks_grid[i][j] is None:
              self._static_blocks_grid[i][j] = _Block(_B.MINE, i, j)
      else:
        for _ in xrange(self.size.x * self.size.y / _MINE_RARITY):
          pos = self._GetRandomPos()
          self._static_blocks_grid[pos.x][pos.y] = _B(type=_B.MINE, pos=pos)

    if power_up_type is not None:
      for _ in xrange(self.size.x * self.size.y / _POWER_UP_RARITY):
        pos = self._GetRandomPos()
        self._static_blocks_grid[pos.x][pos.y] = _B(type=power_up_type, pos=pos)

    self._updates_grid = common.MakeGrid(self.size)
    for i in xrange(self.size.x):
      for j in xrange(self.size.y):
        self._updates_grid[i][j] = (
            self._static_blocks_grid[i][j] or _Block(_B.EMPTY, i, j))
    self._dirty = True

  def SetTerrain(self, block):
    """Sets a new block in the terrain."""
    self._updates_grid[block.pos.x][block.pos.y] = block
    self._static_blocks_grid[block.pos.x][block.pos.y] = (
        None if block.type == _B.EMPTY else block)
    if block.HasField('last_viable_tick'):
      self._expiring_blocks_soonest_first.append(block)
      self._expiring_blocks_soonest_first.sort(key=lambda b: b.last_viable_tick)
    self._dirty = True

  def ClearTerrain(self, pos):
    """Sets a new block in the terrain."""
    self.SetTerrain(_Block(_B.EMPTY, pos.x, pos.y))

  def GetTerrain(self, pos):
    """Gets the terrain block at a coordinate. None if no block is there."""
    return self._static_blocks_grid[pos.x][pos.y]

  def StopTerrainExpiration(self, filter_fn):
    rm_indices = []
    for i, b in enumerate(self._expiring_blocks_soonest_first):
      if filter_fn(b):
        b.ClearField('last_viable_tick')
        rm_indices.append(i)
    for i in reversed(rm_indices):
      del self._expiring_blocks_soonest_first[i]

  def IterAllRockets(self):
    return iter(self._rockets)

  def AddRocket(self, rocket):
    self._rockets.append(rocket)
    self._updates_grid[rocket.pos.x][rocket.pos.y] = rocket
    self._dirty = True

  def _UpdateAsEmpty(self, pos):
    self._updates_grid[pos.x][pos.y] = _Block(_B.EMPTY, pos.x, pos.y)
    self._dirty = True

  def AdvanceBlock(self, b):
    self._UpdateAsEmpty(b.pos)
    b.pos.x = (b.pos.x + b.direction.x) % self.size.x
    b.pos.y = (b.pos.y + b.direction.y) % self.size.y
    # Moving blocks (player heads and rockets) are always included in updates.
    self._dirty = True

  def ExpireBlocks(self, tick):
    rm_indices = []
    for i, rocket in enumerate(self._rockets):
      if rocket.last_viable_tick < tick:
        rm_indices.append(i)
        self._UpdateAsEmpty(rocket.pos)
    for i in reversed(rm_indices):
      del self._rockets[i]

    expiring = self._expiring_blocks_soonest_first
    while expiring and expiring[0].last_viable_tick < tick:
      self.ClearTerrain(expiring.pop(0).pos)

  def GetPlayerHead(self, key):
    return self._player_heads_by_key.get(key)

  def MovePlayerHead(self, key, pos):
    head = self.RemovePlayerHead(key)
    if not head:
      raise KeyError('No player head for %s.' % key)
    head.pos.MergeFrom(pos)
    self._player_heads_by_key[key] = head
    self._updates_grid[head.pos.x][head.pos.y] = head
    self._dirty = True

  def SetPlayerHead(self, key, head):
    self.RemovePlayerHead(key)
    self._player_heads_by_key[key] = head
    self._updates_grid[head.pos.x][head.pos.y] = head
    self._dirty = True

  def RemoveAllPlayerHeads(self):
    for head in self._player_heads_by_key.itervalues():
      self._UpdateAsEmpty(head.pos)
    self._player_heads_by_key = {}

  def RemovePlayerHead(self, key):
    head = self._player_heads_by_key.pop(key, None)
    if head:
      self._UpdateAsEmpty(head.pos)
    return head

  def IterAllPlayerHeads(self):
    return self._player_heads_by_key.itervalues()
