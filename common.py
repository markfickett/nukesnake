# http://pythonhosted.org/Pyro4/intro.html#simple-example
# Start name server with: python -m Pyro4.naming
# Generate the Python protos with: protoc --python_out=. messages.proto

import base64
import random

import Pyro4

import messages_pb2


SERVER_URI_NAME = 'example.server.greeting'


def RegisterProtoSerialization():
  """Registers custom (de)serialization for proto classes.

  See http://pythonhosted.org/Pyro4/clientcode.html#serialization and
  Pyro4's examples/ser_custom/*.py .
  """
  for proto_class in (
      messages_pb2.RegisterRequest,
      messages_pb2.MoveRequest,
      messages_pb2.GameState):
    _RegisterProtoSerializationForClass(proto_class)
  _TestSerialization()


def _RegisterProtoSerializationForClass(proto_class):
  class_name = '%s.%s' % (proto_class.__module__, proto_class.__name__)
  def Serializer(p):
    return {
        '__class__': class_name,
        's': base64.b64encode(p.SerializeToString()),
    }

  def Deserializer(classname, d):
    p = proto_class()
    p.MergeFromString(base64.b64decode(d['s']))
    return p

  Pyro4.util.SerializerBase.register_class_to_dict(proto_class, Serializer)
  Pyro4.util.SerializerBase.register_dict_to_class(class_name, Deserializer)


def _TestSerialization():
  name = 'A Test'
  p = messages_pb2.RegisterRequest(player_secret='hats', player_name=name)
  serializer = Pyro4.util.SerpentSerializer()
  bytes, unused_compressed_status = serializer.serializeData(p)
  p2 = serializer.deserializeData(bytes)
  assert p.player_name == p2.player_name
