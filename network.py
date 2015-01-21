#!/usr/bin/env python
"""Network server (and client) for Nuke Snake, using TCP sockets and protos.

Intro to Python sockets: binarytides.com/python-socket-programming-tutorial/
"""

import errno
import collections
import socket
import time

import google.protobuf.message

import controller
import network_pb2  # protoc --python_out=. *.proto


HOST = 'localhost'
PORT = 9988


class _ProtoSocket(object):
  _STOP = '\xc3\0\0\xdb'  # magic string unlikely to appear in proto stream
  _TIMEOUT = 3.0
  # max size allowed by socket library for UDP is [9214, 9224)
  _BUFFER_SIZE = 9214

  def __init__(self, sock, response_cls, default_addr=None):
    self._sock = sock
    self._sock.settimeout(0.0)  # non-blocking
    self._response_cls = response_cls
    self._buffer = ''
    self._default_addr = default_addr

    self._min_overflow = float('Inf')
    self._max_safe = 0

  def Write(self, proto, dest_addrs=[]):
    data = proto.SerializeToString()
    if self._STOP in data:
      print (
          'Error: stop sequence %r in serialization of proto: %s' %
          (self._STOP, str(proto).replace('\n', ' ')))
      return
    data += self._STOP
    if len(data) > self._BUFFER_SIZE:
      print (
          'Error: serialized proto is %d bytes > buffer size %d bytes: %s...' %
          (len(data), self._BUFFER_SIZE, str(proto).replace('\n', ' ')[:100]))
    try:
      for dest_addr in dest_addrs:
        self._sock.sendto(data, dest_addr)
      if self._default_addr:
        self._sock.sendto(data, self._default_addr)
      self._max_safe = max(self._max_safe, len(data))
    except socket.error, (n, msg):
      print 'Error %d sending: %s' % (n, msg)
      if n == errno.EMSGSIZE:
        self._min_overflow = min(self._min_overflow, len(data))
        print (
            'Attempted to send %d bytes (%d safe, %d overflow).' %
            (len(data), self._max_safe, self._min_overflow))
      else:
        raise

  def _RemoveAndReturnProtoFromBuffer(self):
    proto_data, found_stop, rest = self._buffer.partition(self._STOP)
    if not found_stop:
      return None
    self._buffer = rest
    try:
      return self._response_cls.FromString(proto_data)
    except google.protobuf.message.DecodeError:
      print 'Decoding error of %r.' % proto_data
      return None

  def ReadBlocking(self):
    self._sock.settimeout(self._TIMEOUT)
    while True:
      # may raise socket.timeout
      new_data, sender_addr = self._sock.recvfrom(self._BUFFER_SIZE)
      self._buffer += new_data
      proto = self._RemoveAndReturnProtoFromBuffer()
      if proto:
        self._sock.settimeout(0.0)
        return proto, sender_addr

  def Read(self):
    try:
      new_data, sender_addr = self._sock.recvfrom(self._BUFFER_SIZE)
    except socket.error:
      return None, None  # no data right now
    self._buffer += new_data
    return self._RemoveAndReturnProtoFromBuffer(), sender_addr

  def Close(self):
    self._sock.close()


class Server(object):
  _UPDATE_INTERVAL = 1 / 20.0
  _CLIENT_TIMEOUT = 60.0
  _ClientConnection = collections.namedtuple(
      'ClientConnection', ('activity', 'secrets', 'names'))

  def __init__(self, host, port, width, height):
    self._game = controller.Controller(width, height)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, port))
    self._sock = _ProtoSocket(s, network_pb2.Request)
    print 'Listening on %s:%d.' % (host, port)

    self._active_clients_by_addr = {}
    self._last_state_hash = None

  def ListenAndUpdateForever(self):
    try:
      while True:
        self._ReadClientRequests()
        updates = self._UpdateController()
        self._DistributeUpdates(updates)
        self._UnregisterInactiveClients()
        time.sleep(self._UPDATE_INTERVAL)
    finally:
      print 'Closing listening socket.'
      self._sock.Close()

  def _ReadClientRequests(self):
    request, client_addr = self._sock.Read()
    while request:
      print (
          'Client %s:%d sends: %s' %
          (client_addr[0], client_addr[1], str(request).replace('\n', ' ')))
      if not request.HasField('command'):
        print 'empty request!'
        break
      self._RecordClientActive(client_addr, request.secret, request.name)
      if request.command == network_pb2.Request.REGISTER:
        player_id = self._game.Register(request.secret, request.name)
        print 'Registered player %d with Controller.' % player_id
        self._sock.Write(
            network_pb2.Response(player_id=player_id), [client_addr])
        print 'Wrote registration response.'
      elif request.command == network_pb2.Request.MOVE:
        self._game.Move(request.secret, request.direction)
      elif request.command == network_pb2.Request.ACTION:
        self._game.Action(request.secret)
      elif request.command == network_pb2.Request.UNREGISTER:
        # Client connection info will be auto-removed on timeout.
        self._game.Unregister(request.secret)
      else:
        print 'Unrecognized client request: %s' % request
      request, client_addr = self._sock.Read()

  def _RecordClientActive(self, client_addr, secret, name=None):
    client_connection = self._active_clients_by_addr.get(client_addr)
    if client_connection:
      client_connection.activity.append(time.time())
      client_connection.secrets.add(secret)
      if name:
        client_connection.names.add(name)
    else:
      self._active_clients_by_addr[client_addr] = self._ClientConnection(
          activity=[time.time()],
          secrets=set([secret]),
          names=set([name]) if name else set())

  def _UpdateController(self):
    if self._game.Update():
      self._last_state_hash, new_state = self._game.GetGameState(
          self._last_state_hash)
      if new_state:
        return [new_state]
    return []

  def _DistributeUpdates(self, updates):
    for update_response in updates:
      self._sock.Write(update_response, self._active_clients_by_addr.keys())

  def _UnregisterInactiveClients(self):
    t = time.time()
    to_rm = []
    for addr, conn in self._active_clients_by_addr.iteritems():
      if (t - conn.activity[-1]) > self._CLIENT_TIMEOUT:
        print (
            'Auto un-registered %s (secrets %s) after %ss of inactivity.' %
            (conn.names, conn.secrets, self._CLIENT_TIMEOUT))
        for secret in conn.secrets:
          self._game.Unregister(secret)
        to_rm.append(addr)
    for addr in to_rm:
      del self._active_clients_by_addr[addr]


class Client(object):
  def __init__(self, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._sock = _ProtoSocket(sock, network_pb2.Response, (host, port))

  def Register(self, secret, name):
    register_req = network_pb2.Request(
        secret=secret, command=network_pb2.Request.REGISTER, name=name)
    self._sock.Write(register_req)
    resp, unused_sender_addr = self._sock.ReadBlocking()
    while not resp.HasField('player_id'):
      # Skip server updates unrelated to registration.
      resp, unused_sender_addr = self._sock.ReadBlocking()
    return resp.player_id

  def Move(self, secret, direction):
    self._sock.Write(network_pb2.Request(
        secret=secret, command=network_pb2.Request.MOVE, direction=direction))

  def Action(self, secret):
    self._sock.Write(network_pb2.Request(
        secret=secret, command=network_pb2.Request.ACTION))

  def GetUpdates(self):
    updates = []
    resp, unused_sender_addr = self._sock.Read()
    while resp:
      updates.append(resp)
      resp, unused_sender_addr = self._sock.Read()
    return updates

  def Unregister(self, secret):
    self._sock.Write(network_pb2.Request(
        secret=secret, command=network_pb2.Request.UNREGISTER))


if __name__ == '__main__':
  server = Server('', PORT, 78, 23)
  server.ListenAndUpdateForever()
