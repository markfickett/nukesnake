"""Rules for scoring and for starting/ending rounds.

Using different scorers allows different game modes.
"""


import logging

from common import game_pb2


_B = game_pb2.Block


class _Base(object):
  def __init__(self):
    self._player_infos_by_id = {}

  def AddPlayer(self, info):
    info.score = 0
    self._player_infos_by_id[info.player_id] = info

  def RemovePlayer(self, player_id):
    del self._player_infos_by_id[player_id]

  @property
  def _num_alive(self):
    return len(filter(
        lambda info: info.alive, self._player_infos_by_id.itervalues()))

  def IsGameOver(self):
    return False

  def UseRespawn(self):
    return False

  def TerrainChanged(self, blocks):
    pass

  def ItemUsed(self, player_id, item_type):
    if item_type in (_B.NUKE,):
      self._player_infos_by_id[player_id].score += 1

  def Reset(self):
    for info in self._player_infos_by_id.itervalues():
      info.score = 0


class Battle(_Base):
  """PvP: Surviving longer results in a higher score."""
  def __init__(self):
    _Base.__init__(self)

  def CanStartRound(self):
    return len(self._player_infos_by_id) > 1

  def IsRoundEnd(self):
    return self._num_alive <= 1

  def ItemDestroyed(self, by_player_id, item):
    if item.type == _B.PLAYER_HEAD:
      if by_player_id is not None:
        self._player_infos_by_id[by_player_id].score += (
          -5 if by_player_id == item.player_id else 5)
      for info in self._player_infos_by_id.itervalues():
        if info.alive:
          info.score += 1


class ClearMines(_Base):
  """Cooperative: Clear all the mines and nukes to proceed to the next round."""
  _TYPES_TO_CLEAR = (_B.MINE, _B.NUKE)
  _LIVES_PER_PLAYER = 3
  def __init__(self):
    _Base.__init__(self)
    self._mine_coords = set()
    self._lives = 0

  def CanStartRound(self):
    """Requires at least one player."""
    return len(self._player_infos_by_id) > 0

  def UseRespawn(self):
    if self._lives > 0:
      self._lives -= 1
      return True
    else:
      return False

  def TerrainChanged(self, blocks):
    """Records the new mines. Penalizes everyone for mines not cleared."""
    for info in self._player_infos_by_id.itervalues():
      info.score -= len(self._mine_coords)
    self._mine_coords = set()
    for block in blocks:
      if block.type in self._TYPES_TO_CLEAR:
        self._mine_coords.add((block.pos.x, block.pos.y))
    logging.debug('%d mines to clear', len(self._mine_coords))

  def IsRoundEnd(self):
    """Returns True when all explosives are cleared or everyone is dead."""
    return len(self._mine_coords) <= 0

  def AddPlayer(self, *args):
    _Base.AddPlayer(self, *args)
    self._lives += self._LIVES_PER_PLAYER

  def RemovePlayer(self, *args):
    _Base.RemovePlayer(self, *args)
    self._lives -= self._LIVES_PER_PLAYER

  def IsGameOver(self):
    return self._num_alive <= 0

  def ItemDestroyed(self, by_player_id, item):
    """Awards points for clearing mines, penalizes for killing players."""
    if item.type in self._TYPES_TO_CLEAR:
      if by_player_id is not None:
        self._player_infos_by_id[by_player_id].score += 1
      coord = (item.pos.x, item.pos.y)
      # In big explosions, some get removed twice.
      if coord in self._mine_coords:
        self._mine_coords.remove(coord)
      logging.debug('%d mines left', len(self._mine_coords))
      if len(self._mine_coords) <= 0:
        for info in self._player_infos_by_id.itervalues():
          if info.alive:
            info.score += 20
    elif item.type is _B.PLAYER_HEAD:
      if by_player_id is not None:
        self._player_infos_by_id[by_player_id].score -= 5
      for info in self._player_infos_by_id.itervalues():
        info.score -= 1
