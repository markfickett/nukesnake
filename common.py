def MakeGrid(size):
  grid = []
  for x in range(size.x):
    grid.append([None] * size.y)
  return grid
