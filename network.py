#!/usr/bin/env python
"""Network server (and client) for Nuke Snake, using TCP sockets and protos.

Intro to Python sockets: binarytides.com/python-socket-programming-tutorial/
"""

import socket
import time

import google.protobuf.message

import controller
import network_pb2  # protoc --python_out=. *.proto


HOST = 'localhost'
PORT = 9988


class DisconnectedError(RuntimeError):
  pass


class _ProtoSocket(object):
  _STOP = '\xc3\0\0\xdb'  # magic string unlikely to appear in proto stream
  _TIMEOUT = 3.0

  def __init__(self, sock, response_cls):
    self._sock = sock
    self._sock.settimeout(0.0)  # non-blocking
    self._response_cls = response_cls
    self._buffer = ''

  def Write(self, proto):
    data = proto.SerializeToString()
    if self._STOP in data:
      print (
          'Error: stop sequence %r in serialization of proto %s.' %
          (self._STOP, str(proto).replace('\n', ' ')))
      return
    self._sock.settimeout(self._TIMEOUT)
    try:
      self._sock.sendall(data + self._STOP)
    except socket.error:
      raise DisconnectedError()
    finally:
      self._sock.settimeout(0.0)

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
      self._buffer += self._sock.recv(4096)
      proto = self._RemoveAndReturnProtoFromBuffer()
      if proto:
        self._sock.settimeout(0.0)
        return proto

  def Read(self):
    new_data = ''
    try:
      new_data += self._sock.recv(4096)
    except socket.error:
      return  # connection open, no data
    if not new_data:
      raise DisconnectedError()
    self._buffer += new_data
    return self._RemoveAndReturnProtoFromBuffer()

  def Close(self):
    self._sock.close()


class Server(object):
  _MAX_CONNECTIONS = 10
  _UPDATE_INTERVAL = 1 / 20.0

  def __init__(self, host, port, width, height):
    self._game = controller.Controller(width, height)
    self._listening_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._listening_sock.bind((host, port))
    self._listening_sock.listen(self._MAX_CONNECTIONS)
    print (
        'Listening for up to %d connections on %s:%d.' %
        (self._MAX_CONNECTIONS, host, port))
    self._listening_sock.settimeout(0.0)
    self._client_conns_and_secrets = []
    self._last_state_hash = None

  def ListenAndUpdateForever(self):
    try:
      while True:
        self._AcceptNewConnections()
        self._ReadCommandRequests()
        updates = self._UpdateController()
        self._DistributeUpdates(updates)
        time.sleep(self._UPDATE_INTERVAL)
    finally:
      print 'Closing all connections.'
      self._listening_sock.close()
      for client_socket, _ in self._client_conns_and_secrets:
        client_socket.Close()

  def _AcceptNewConnections(self):
    got_new_connection = True
    while got_new_connection:
      try:
        raw_socket, addr = self._listening_sock.accept()
        print ('New client connection from %s:%d.' % addr)
        client_socket = _ProtoSocket(raw_socket, network_pb2.Request)
        self._client_conns_and_secrets.append((client_socket, []))
      except socket.error:
        got_new_connection = False

  def _ReadSingleCommandRequest(self, client_socket, secrets):
    request = client_socket.Read()
    while request:
      print 'Got client command request: %s' % str(request).replace('\n', ' ')
      if request.command == network_pb2.Request.REGISTER:
        player_id = self._game.Register(request.secret, request.name)
        print 'Registered player %d with Controller.' % player_id
        client_socket.Write(network_pb2.Response(player_id=player_id))
        secrets.append(request.secret)
        print 'Wrote registration response.'
      elif request.command == network_pb2.Request.MOVE:
        self._game.Move(request.secret, request.direction)
      elif request.command == network_pb2.Request.ACTION:
        self._game.Action(request.secret)
      else:
        print 'Unrecognized client request: %s' % request
      request = client_socket.Read()

  def _ReadCommandRequests(self):
    self._ForEachClientSocket(self._ReadSingleCommandRequest)

  def _UpdateController(self):
    if self._game.Update():
      self._last_state_hash, new_state = self._game.GetGameState(
          self._last_state_hash)
      if new_state:
        return [new_state]
    return []

  def _WriteSingleUpdate(self, client_socket, secrets, update_response):
    client_socket.Write(update_response)

  def _DistributeUpdates(self, updates):
    for update_response in updates:
      self._ForEachClientSocket(self._WriteSingleUpdate, update_response)

  def _ForEachClientSocket(self, fn, *args):
    rm_indices = []
    for i, (client_socket, secrets) in enumerate(
        self._client_conns_and_secrets):
      try:
        fn(client_socket, secrets, *args)
      except DisconnectedError:
        print 'client disconnected (in read)'
        rm_indices.append(i)
    for i in reversed(rm_indices):
      _, secrets = self._client_conns_and_secrets.pop(i)
      for secret in secrets:
        self._game.Unregister(secret)


class Client(object):
  def __init__(self, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    self._sock = _ProtoSocket(sock, network_pb2.Response)

  def Register(self, secret, name):
    self._sock.Write(network_pb2.Request(
        secret=secret,
        name=name,
        command=network_pb2.Request.REGISTER))
    resp = self._sock.ReadBlocking()
    while not resp.HasField('player_id'):
      # Skip server updates unrelated to registration.
      resp = self._sock.ReadBlocking()
    return resp.player_id

  def Move(self, secret, direction):
    self._sock.Write(network_pb2.Request(
        secret=secret,
        command=network_pb2.Request.MOVE,
        direction=direction))

  def Action(self, secret):
    self._sock.Write(network_pb2.Request(
        secret=secret,
        command=network_pb2.Request.ACTION))

  def GetUpdates(self):
    updates = []
    resp = self._sock.Read()
    while resp:
      updates.append(resp)
      resp = self._sock.Read()
    return updates


if __name__ == '__main__':
  server = Server('', PORT, 78, 23)
  server.ListenAndUpdateForever()
