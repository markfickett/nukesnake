import common
import game_pb2
import random


class World(object):
  """Blocks in the world and management for tracking diffs."""
  def __init__(self, width, height):
    # Readonly, but exposed for common use in controller.
    self.size = game_pb2.Coordinate(x=max(4, width), y=max(4, height))

  def GetRandomPos(self):
    """Returns a random coordinate within the world (and not in the walls)."""
    return game_pb2.Coordinate(
      x=random.randint(1, self.size.x - 2),
      y=random.randint(1, self.size.y - 2))
