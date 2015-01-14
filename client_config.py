"""Client control and behavior configuration."""

import curses
import messages_pb2
_B = messages_pb2.Block


# Characters used as player icons, for the snakes' heads. Assigned in the order
# the players join the game. For more characters, see:
# alanflavell.org.uk/unicode/unidata25.html and unicode-table.com/
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
  _B.PLAYER_TAIL: u'\N{DARK SHADE}',
  _B.WALL: u'\N{FULL BLOCK}',
  _B.ROCKET: u'\N{WHITE STAR}',
  _B.AMMO: u'\N{Tamil Sign Visarga}',
  _B.MINE: u'\N{REFERENCE MARK}',
}
# A fallback for block types with no other character assigned.
DEFAULT_BLOCK_CHARACTER = '?'


# Colors listed with the different block types to which they apply. (Other
# types are rendered white.)
BLOCK_FOREGROUNDS = {
  curses.COLOR_GREEN: (_B.WALL,),
  curses.COLOR_MAGENTA: (_B.MINE, _B.ROCKET),
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
MOVE_KEYS = (
    # Player 1
    {
       ord('q'): (-1, -1),
       ord('w'): (0, -1),
       ord('e'): (1, -1),
       ord('a'): (-1, 0),
       ord('s'): (0, 1),
       ord('d'): (1, 0),
       ord('z'): (-1, 1),
       ord('x'): (0, 1),
       ord('c'): (1, 1),
    },
    # Player 2
    {
       ord('u'): (-1, -1),
       ord('i'): (0, -1),
       ord('o'): (1, -1),
       ord('j'): (-1, 0),
       ord('k'): (0, 1),
       ord('l'): (1, 0),
       ord('m'): (-1, 1),
       ord(','): (0, 1),
       ord('.'): (1, 1),
    },
)
# List of the action keys (to start the game or shoot), in player order.
ACTION_KEYS = (
    ord('`'),
    ord('\\'),
)


# Process player commands and poll for server updates at this interval.
UPDATE_INTERVAL_SEC = 1.0 / 120.0
