import logging

def MakeGrid(size):
  grid = []
  for x in range(size.x):
    grid.append([None] * size.y)
  return grid


def ConfigureLogging():
  logging.basicConfig(
      format='%(levelname)s %(asctime)s %(filename)s:%(lineno)s: %(message)s',
      level=logging.INFO)
