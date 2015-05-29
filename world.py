import common
import game_pb2


class World(object):
  """Blocks in the world and management for tracking diffs."""
  def __init__(self, width, height):
    # Readonly, but exposed for common use in controller.
    self.size = game_pb2.Coordinate(x=max(4, width), y=max(4, height))
