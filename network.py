#!/usr/bin/env python
"""Network server (and client interface) for Nuke Snake.

Example:
  # Run a server with a 200x50 block world.
  %(prog)s --width 200 --height 50

The server uses UDP sockets and protobufs for communication. Intro to Python
sockets: binarytides.com/python-socket-programming-tutorial/
"""

import argparse
import errno
import collections
import logging
import socket
import threading
import time
import zlib

import google.protobuf.message

import common
import controller
import network_pb2  # protoc --python_out=. *.proto


PORT = 9988


class _ProtoSocket(object):
  _STOP = '\xc3\0\0\xdb'  # magic string unlikely to appear in proto stream
  _TIMEOUT = 3.0
  # max size allowed by socket library for UDP is [9214, 9224)
  _BUFFER_SIZE = 9214
  _CHUNK_REPORT_INTERVAL = 50
  _Segment = collections.namedtuple(
      'Segment', ('chunks', 'indices', 'has_last'))

  def __init__(self, sock, response_cls, default_addr=None):
    self._sock = sock
    self._sock.settimeout(0.0)  # non-blocking
    self._response_cls = response_cls
    self._buffer = ''
    self._default_addr = default_addr

    self._next_segment_id = 1
    self._segments_by_id = collections.defaultdict(
        lambda: self._Segment(chunks=[], indices=set(), has_last=[False]))

    # stats on packet size
    self._num_writes = 0
    self._num_chunked = 0
    self._min_overflow = float('Inf')
    self._max_safe = 0

  def Write(self, proto, dest_addrs=[], chunked=False):
    # Note zlib gets consistent 60% compression on large (200x50) worlds.
    data = zlib.compress(proto.SerializeToString()) + self._STOP
    if self._num_writes >= self._CHUNK_REPORT_INTERVAL:
      if self._num_chunked > 0:
        logging.info(
            '%d of last %d writes chunked (%d%%).',
            self._num_chunked,
            self._num_writes,
            int(100 * float(self._num_chunked)/self._num_writes))
      self._num_writes = 0
      self._num_chunked = 0
    if not chunked:
      self._num_writes += 1
    if len(data) > self._BUFFER_SIZE:
      if hasattr(proto, 'chunk_info') and not chunked:
        self._num_chunked += 1
        self._WriteChunked(proto, len(data), dest_addrs)
      else:
        logging.error(
            'Error: Non-chunkable proto is %d bytes > buffer %d bytes: %s...',
            len(data), self._BUFFER_SIZE, str(proto).replace('\n', ' ')[:100])
      return
    try:
      for dest_addr in dest_addrs:
        self._sock.sendto(data, dest_addr)
      if self._default_addr:
        self._sock.sendto(data, self._default_addr)
      self._max_safe = max(self._max_safe, len(data))
    except socket.error, (n, msg):
      logging.error('Error %d sending: %s' % (n, msg))
      if n == errno.EMSGSIZE:
        self._min_overflow = min(self._min_overflow, len(data))
        logging.error(
            'Attempted to send %d bytes (%d safe, %d overflow).',
            len(data), self._max_safe, self._min_overflow)
      else:
        raise

  def _WriteChunked(self, proto, oversize, dest_addrs):
    # TODO: Generalize (for request too / for arbitrary fields)?
    num_chunks = oversize / self._BUFFER_SIZE + 2
    remaining_block_list = list(proto.block)
    blocks_per_chunk = (len(remaining_block_list) / num_chunks) + 1
    del proto.block[:]
    chunk_index = 0
    while remaining_block_list:
      block_chunk = remaining_block_list[:blocks_per_chunk]
      remaining_block_list = remaining_block_list[blocks_per_chunk:]
      chunk = proto.__class__(
          block=block_chunk,
          chunk_info=network_pb2.Chunk(
              segment_id=self._next_segment_id,
              chunk_index=chunk_index,
              last_chunk=not remaining_block_list))
      chunk.MergeFrom(proto)
      self.Write(chunk, dest_addrs, chunked=True)
      chunk_index += 1
    self._next_segment_id += 1

  def _RemoveAndReturnChunked(self, chunk):
    segment = self._segments_by_id[chunk.chunk_info.segment_id]
    segment.indices.add(chunk.chunk_info.chunk_index)
    segment.chunks.append(chunk)
    segment.has_last[0] |= chunk.chunk_info.last_chunk
    if segment.has_last[0] and max(segment.indices) == len(segment.chunks) - 1:
      del self._segments_by_id[chunk.chunk_info.segment_id]
      ordered = segment.chunks
      ordered.sort(key=lambda chunk: chunk.chunk_info.chunk_index)
      first = ordered[0]
      for chunk in ordered[1:]:
        first.block.extend(chunk.block)
      return first
    return None

  def _RemoveAndReturnProtoFromBuffer(self):
    proto_data, found_stop, rest = self._buffer.partition(self._STOP)
    if not found_stop:
      return None
    self._buffer = rest
    try:
      proto = self._response_cls.FromString(zlib.decompress(proto_data))
      if hasattr(proto, 'chunk_info') and proto.HasField('chunk_info'):
        return self._RemoveAndReturnChunked(proto)
      else:
        return proto
    except google.protobuf.message.DecodeError:
      logging.error('Decoding error of %r.', proto_data)
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


_UPDATE_INTERVAL = 1 / 20.0


class Server(object):
  _CLIENT_ROUNDS_TIMEOUT = 3
  _ClientConnection = collections.namedtuple(
      'ClientConnection', ('activity', 'secrets', 'names'))

  def __init__(self, host, port, width, height, starting_round):
    self._game = controller.Controller(width, height, starting_round)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, port))
    self._sock = _ProtoSocket(s, network_pb2.Request)
    logging.info('Listening on %s:%d.', host, port)

    self._active_clients_by_addr = {}
    self._last_round = 0
    self._last_state_hash = None

  def ListenAndUpdateForever(self):
    try:
      while True:
        t = time.time()
        self._ReadClientRequests()
        updates = self._UpdateController()
        self._DistributeUpdates(updates)
        self._UnregisterInactiveClients()
        used_dt = time.time() - t
        if used_dt < _UPDATE_INTERVAL:
          time.sleep(_UPDATE_INTERVAL - used_dt)
    finally:
      logging.info('Closing listening socket.')
      self._sock.Close()

  def _ReadClientRequests(self):
    request, client_addr = self._sock.Read()
    while request:
      logging.debug(
          'Client %s:%d sends: %s',
          client_addr[0], client_addr[1], str(request).replace('\n', ' '))
      if not request.HasField('command'):
        logging.error('Ignoring empty request!')
        break
      self._RecordClientActive(client_addr, request.secret, request.name)
      if request.command == network_pb2.Request.REGISTER:
        player_id = self._game.Register(request.secret, request.name)
        logging.info('Registered player %d with Controller.', player_id)
        self._sock.Write(
            network_pb2.Response(player_id=player_id), [client_addr])
      elif request.command == network_pb2.Request.MOVE:
        self._game.Move(request.secret, request.direction)
      elif request.command == network_pb2.Request.ACTION:
        self._game.Action(request.secret)
      elif request.command == network_pb2.Request.UNREGISTER:
        # Client connection info will be auto-removed on timeout.
        self._game.Unregister(request.secret)
      else:
        logging.error('Ignoring unrecognized client request: %s', request)
      request, client_addr = self._sock.Read()

  def _RecordClientActive(self, client_addr, secret, name=None):
    client_connection = self._active_clients_by_addr.get(client_addr)
    if client_connection:
      del client_connection.activity[:]
      client_connection.activity.append(self._last_round)
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
        self._last_round = new_state.round_num
        return [new_state]
    return []

  def _DistributeUpdates(self, updates):
    for update_response in updates:
      self._sock.Write(update_response, self._active_clients_by_addr.keys())

  def _UnregisterInactiveClients(self):
    to_rm = []
    for addr, conn in self._active_clients_by_addr.iteritems():
      if (self._last_round - conn.activity[-1]) > self._CLIENT_ROUNDS_TIMEOUT:
        logging.info(
            'Auto un-registered %s (secrets %s) after %s rounds of inactivity.',
            conn.names, conn.secrets, self._CLIENT_ROUNDS_TIMEOUT)
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
    try:
      resp, unused_sender_addr = self._sock.ReadBlocking()
      while not resp.HasField('player_id'):
        # Skip server updates unrelated to registration.
        resp, unused_sender_addr = self._sock.ReadBlocking()
    except socket.timeout, e:
      raise socket.timeout(
          errno.EREMOTE,
          e,
          'Timeout waiting for registration reply. Do you need to start a'
          ' server with network.py or specify --host ?')
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


class LocalThreadClient(threading.Thread):
  def __init__(self, width, height):
    self._controller = controller.Controller(width, height)
    self._last_state_hash = None
    self._last_state = None
    self._lock = threading.Lock()
    threading.Thread.__init__(self)

  def Register(self, secret, name):
    with self._lock:
      return self._controller.Register(secret, name)

  def Unregister(self, secret):
    with self._lock:
      return self._controller.Unregister(secret, name)

  def Move(self, secret, direction):
    with self._lock:
      return self._controller.Move(secret, direction)

  def Action(self, secret):
    with self._lock:
      return self._controller.Action(secret)

  def GetUpdates(self):
    with self._lock:
      return [self._last_state]

  def run(self):
    while True:
      t = time.time()
      with self._lock:
        new_state = None
        if self._controller.Update():
          self._last_state_hash, new_state = self._controller.GetGameState(
              self._last_state_hash)
        if new_state:
          self._last_state = new_state
      used_dt = time.time() - t
      if used_dt < _UPDATE_INTERVAL:
        time.sleep(_UPDATE_INTERVAL - used_dt)


if __name__ == '__main__':
  common.ConfigureLogging()
  summary_line, _, main_doc = __doc__.partition('\n\n')
  parser = argparse.ArgumentParser(
      description=summary_line,
      epilog=main_doc,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--host', default='',
      help='Hostname to bind to when serving network play.')
  controller.AddControllerArgs(parser)
  args = parser.parse_args()

  server = Server(args.host, PORT, args.width, args.height, args.round)
  server.ListenAndUpdateForever()
