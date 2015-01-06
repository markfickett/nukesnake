# http://pythonhosted.org/Pyro4/intro.html#simple-example

import Pyro4

import messages_pb2
import server


if __name__ == '__main__':
  server.RegisterProtoSerialization()

  name = raw_input('What is your name? ').strip()

  greeting_maker = Pyro4.Proxy('PYRONAME:%s' % server.SERVER_URI_NAME)
  response = greeting_maker.get_fortune(messages_pb2.Request(name=name))
  print (
      '%s Your lucky number is %d.'
      % (response.fortune, response.lucky_number))
