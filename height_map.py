"""Random smoothed height-map generation, for terrain.

Drawing inspiration from redblobgames.com/articles/noise/introduction.html .
"""

import random


def MakeHeightMap(width, height, min_value, max_value, blur_size=2):
  rand_vals = []
  smoothed = []
  for _ in xrange(width):
    row = []
    for _ in xrange(height):
      row.append(random.randint(min_value, max_value))
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
  grid = MakeHeightMap(50, 200, 0, 30, blur_size=4)
  if False:
    for row in grid:
      for v in row:
        print ('%2d' % v),
      print ''
  for row in grid:
    row_str = []
    for v in row:
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
