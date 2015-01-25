"""Random smoothed height-map generation, for terrain.

Drawing inspiration from redblobgames.com/articles/noise/introduction.html .
"""

import math
import random


def MakeHeightMap(
    width,
    height,
    min_value,
    max_value,
    blur_size=2,
    ripple_amt=2,
    ripple_period=50):
  rand_vals = []
  smoothed = []
  for i in xrange(width):
    row = []
    for _ in xrange(height):
      row.append(
          random.randint(min_value, max_value) +
          ripple_amt * math.sin(i / (ripple_period / (math.pi * 2))))
    rand_vals.append(row)
    smoothed.append([None] * height)
  area = (2 * blur_size + 1) ** 2
  for x in xrange(width):
    for y in xrange(height):
      v = 0
      for i in xrange(-blur_size, blur_size + 1):
        for j in xrange(-blur_size, blur_size + 1):
          v += rand_vals[(x + i) % width][(y + j) % height]
      smoothed[x][y] = v / area
  return smoothed


if __name__ == '__main__':
  width, height = (200, 50)
  grid = MakeHeightMap(width, height, 0, 30)
  if False:
    for row in grid:
      for v in row:
        print ('%2d' % v),
      print ''
  for j in xrange(height):
    row_str = []
    for i in xrange(width):
      v = grid[i][j]
      if v >= 17:
        c = u'\N{FULL BLOCK}'
      elif v >= 16:
        c = u'\N{MEDIUM SHADE}'
      elif v >= 15:
        c = u'\N{LIGHT SHADE}'
      else:
        c = ' '
      row_str.append(c)
    print ''.join(row_str)
