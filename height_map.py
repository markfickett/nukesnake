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
    ripple_amt=(0, 0),
    ripple_period=(50, 30)):
  rand_vals = []
  smoothed = []
  scale_x = 1.0 / (ripple_period[0] / (math.pi * 2))
  scale_y = 1.0 / (ripple_period[1] / (math.pi * 2))
  for i in xrange(width):
    row = []
    for j in xrange(height):
      row.append(
          random.randint(min_value, max_value) +
          ripple_amt[0] * math.sin(i * scale_x) +
          ripple_amt[1] * math.sin(j * scale_y))
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
  grid = MakeHeightMap(width, height, 0, 30, ripple_amt=(2, 1))
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
