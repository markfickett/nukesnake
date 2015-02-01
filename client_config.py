"""Client key controls and behavior configuration."""

from common import game_pb2
import curses
_B = game_pb2.Block


# Characters used as player icons, for the snakes' heads. Assigned in the order
# the players join the game. For more characters, see:
# alanflavell.org.uk/unicode/unidata25.html and unicode-table.com
PLAYER_ICONS = [
    u'\N{UMBRELLA}',
    '$',
    u'\N{Circled Dot Operator}',
    u'\N{Ohm Sign}',
]
# Extend the player icons to include the alphabet, after more decorative
# characters are used up.
PLAYER_ICONS += [chr(c) for c in range(ord('A'), ord('Z') + 1)]


# Characters used to render the various items in the game world.
BLOCK_CHARACTERS = {
  _B.PLAYER_TAIL: u'\N{Dark Shade}',
  _B.WALL: u'\N{Full Block}',
  _B.ROCKET: u'\N{White Star}',
  _B.AMMO: u'\N{Tamil Sign Visarga}',
  _B.NUKE: u'\N{Radioactive Sign}',
  _B.MINE: u'\N{Reference Mark}',
  _B.ROCK: u'\N{Black Shogi Piece}',
  _B.BROKEN_ROCK: u'\N{Reversed Rotated Floral Heart Bullet}',
  _B.TREE: u'\N{Apl Functional Symbol Delta Stile}',

  _B.STAY_STILL: u'\N{Black Chess Rook}',
  _B.FAST: u'\U0001f407',  # Rabbit
  _B.TELEPORT: u'\U0001f680',  # Rocket
}
# A fallback for block types with no other character assigned.
DEFAULT_BLOCK_CHARACTER = '?'


# Colors listed with the different block types to which they apply. (Other
# types are rendered white.)
BLOCK_FOREGROUNDS = {
  curses.COLOR_GREEN: (_B.WALL, _B.TREE),
  curses.COLOR_MAGENTA: (_B.MINE, _B.ROCKET),
  curses.COLOR_YELLOW: (_B.NUKE,),
}
BG_COLOR = curses.COLOR_BLACK
# Colors to be used for players, used in the order players join.
PLAYER_COLORS = (
  curses.COLOR_CYAN,
  curses.COLOR_RED,
  curses.COLOR_YELLOW,
  curses.COLOR_WHITE,
)


# Mapping from keys to the direction it will move the player's snake.
_ORDERED_COORDS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (0, 1),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)
MOVE_KEYS = [
    {ord(k): c for k, c in zip(movement_keys, _ORDERED_COORDS)}
    for movement_keys in (
        'qweasdzxc',
        'uiojklm,.',
        'rtyfghvbn')]
# List of the action keys (to start the game or shoot), in player order.
ACTION_KEYS = (
    ord(' '),
    ord(';'),
    ord('\\'),
)


BLOCK_DESCRIPTIONS = {
    _B.WALL: 'Walls around the world. Shoot off both sides and you can wrap.',
    _B.AMMO: 'Each ammo you pick up lets you shoot 3 rockets.',
    _B.ROCKET: '',
    _B.MINE: 'Blows up when you shoot it or run into it.',
    _B.ROCK: 'Steer clear. Takes two shots to destroy.',
    _B.BROKEN_ROCK: '',
    _B.TREE: 'Steer clear. Takes one shot to destroy.',
    _B.STAY_STILL: 'Power-up, freezes other players.',
    _B.FAST: 'Lets you go as fast as a rocket.',
    _B.TELEPORT: 'Teleport randomly each time you press action while it\'s on.',
    _B.NUKE: 'When you shoot, it\'s like a super-mine goes off.',
}


# Process player commands and poll for server updates at this interval.
UPDATE_INTERVAL_SEC = 1.0 / 120.0
