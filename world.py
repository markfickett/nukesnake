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

_B = game_pb2.Block


class World(object):
  """Blocks in the world and management for tracking diffs."""
  def __init__(self, width, height):
    # Readonly, but exposed for common use in controller.
    self.size = game_pb2.Coordinate(x=max(4, width), y=max(4, height))
    self._updates_grid = common.MakeGrid(self.size)
    self._static_blocks_grid = common.MakeGrid(self.size)

  def GetRandomPos(self):
    """Returns a random coordinate within the world (and not in the walls)."""
    return game_pb2.Coordinate(
      x=random.randint(1, self.size.x - 2),
      y=random.randint(1, self.size.y - 2))

  def RebuildStaticBlocks(self, power_up_type):
    self._static_blocks_grid = common.MakeGrid(self.size)
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
        pos = self.GetRandomPos()
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
          pos = self.GetRandomPos()
          self._static_blocks_grid[pos.x][pos.y] = _B(type=_B.MINE, pos=pos)

    if power_up_type is not None:
      for _ in xrange(self.size.x * self.size.y / _POWER_UP_RARITY):
        pos = self.GetRandomPos()
        self._static_blocks_grid[pos.x][pos.y] = _B(type=power_up_type, pos=pos)

    self._updates_grid = common.MakeGrid(self.size)
    for i in xrange(self.size.x):
      for j in xrange(self.size.y):
        b = self._static_blocks_grid[i][j]
        self._updates_grid[i][j] = _B.EMPTY if b is None else b
