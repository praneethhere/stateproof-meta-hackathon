"""Exercise six immediate lost-reply retries on a private Redis 8.6+ Streams server."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

DOC = 'https://redis.io/docs/latest/develop/data-types/streams/idempotency/'
INTENT = 'shipment-1042'
# Each pair describes the first write and retry sent by the test producer.
CASES = (
    ('plain', 'Business ID in the message body', 'plain', False, False),
    ('explicit', 'Same producer and idempotent ID', 'IDMP', False, False),
    ('producer', 'Producer changes during failover', 'IDMP', True, False),
    ('auto', 'Same producer and identical contents', 'IDMPAUTO', False, False),
    ('auto_content', 'Retry changes the attempt field', 'IDMPAUTO', False, True),
    ('explicit_content', 'Explicit ID survives a changed attempt field', 'IDMP', False, True),
)


def encode(command):
    args = [arg.encode('utf-8') for arg in command]
    return (f'*{len(args)}\r\n'.encode() +
            b''.join(f'${len(arg)}\r\n'.encode() + arg + b'\r\n' for arg in args))


def reply(stream):
    header = stream.readline(4096)
    if not header.endswith(b'\r\n'):
        raise ValueError('Incomplete Redis response')
    kind, value = header[:1], header[1:-2]
    if kind == b'-':
        raise RuntimeError('Redis rejected the test command: ' + value.decode())
    if kind == b'+':
        return value.decode()
    if kind == b':':
        return int(value)
    if kind == b'*':
        return [reply(stream) for _ in range(int(value))]
    if kind == b'$':
        size = int(value)
        if size == -1:
            return None
        data = stream.read(size)
        if len(data) != size or stream.read(2) != b'\r\n':
            raise ValueError('Incomplete Redis bulk response')
        return data.decode()
    raise ValueError('Unexpected Redis response type')


def call(address, *args):
    with socket.create_connection(address, timeout=3) as client:
        client.sendall(encode(args))
        with client.makefile('rb') as stream:
            return reply(stream)


@contextmanager
def isolated_server(binary):
    with tempfile.TemporaryDirectory(prefix='stateproof-redis-') as work:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as choice:
            choice.bind(('127.0.0.1', 0))
            address = choice.getsockname()
        process = subprocess.Popen([binary, '--bind', address[0], '--port', str(address[1]), '--protected-mode', 'yes',
                                    '--dir', work, '--save', '', '--appendonly', 'no', '--daemonize', 'no'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('The isolated Redis server stopped during startup')
                try:
                    info = dict(line.split(':',1) for line in call(address,'INFO','server').splitlines() if ':' in line)
                except (ConnectionError, TimeoutError):
                    time.sleep(.04)
                    continue
                if info.get('process_id') != str(process.pid):
                    raise RuntimeError('Unexpected server identity; aborting before any writes')
                break
            else:
                raise RuntimeError('Timed out waiting for the test server')
            version = info['redis_version']
            if tuple(int(v) for v in version.split('.')[:2]) < (8,6):
                raise ValueError(f'Redis 8.6 or later is required, found {version}')
            yield address, version
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def add_command(stream, mode, producer, attempt):
    flags = [] if mode == 'plain' else [mode, producer]
    if mode == 'IDMP':
        flags.append(INTENT)
    return ['XADD', stream, *flags, '*', 'shipment', INTENT, 'attempt', str(attempt)]


def measure(address, case):
    name, title, mode, changed_producer, changed_content = case
    stream = 'crashlab-' + name
    first = add_command(stream, mode, 'producer-A', 1)
    retry = add_command(stream, mode, 'producer-B' if changed_producer else 'producer-A', 2 if changed_content else 1)
    with socket.create_connection(address, timeout=3) as producer:
        producer.sendall(encode(first))
        deadline = time.monotonic() + 3
        while call(address, 'XLEN', stream) != 1:
            if time.monotonic() > deadline:
                raise RuntimeError('Observer never saw the first append')
            time.sleep(.005)
        # Close the producer connection without reading its acknowledgement.
    retry_reply = call(address, *retry)
    rows = call(address,'XRANGE',stream,'-','+')
    entries = [{'stream_id':sid, 'fields':dict(zip(fields[::2],fields[1::2]))} for sid, fields in rows]
    return {'id': name, 'title': title, 'first_command': first, 'retry_command': retry,
            'observed_before_retry': 1, 'retry_reply': retry_reply, 'entries': entries, 'entry_count': len(entries)}


def run(binary):
    with isolated_server(binary) as (address, version):
        cases = [measure(address, case) for case in CASES]
    result = {'schema':'stateproof-redis-streams-v1', 'engine': 'Redis', 'version': version,
              'created_utc': datetime.now(timezone.utc).isoformat(), 'reference': DOC,
              'method': 'The server accepted the first append. A separate connection checked XLEN before the producer closed its socket without reading the reply. After an immediate retry, a separate connection queried XRANGE.',
              'scope':'Disposable loopback server; synthetic shipment intents; no model call; no persistence, failover process, window expiration or downstream delivery was measured.',
              'cases':cases}
    result['sha256'] = hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default=shutil.which('redis-server'), help='Path to the Redis 8.6+ server executable')
    parser.add_argument('--out', type=Path, help='New JSON receipt path')
    args = parser.parse_args()
    if not args.server:
        parser.error('Install Redis 8.6+ or pass --server /path/to/redis-server')
    if args.out and args.out.exists():
        parser.error('Choose a new receipt path')
    result = run(args.server)
    if args.out:
        with args.out.open('x', encoding='utf8') as file:
            json.dump(result, file, indent=2)
            file.write('\n')
    for case in result['cases']:
        print(f"{case['entry_count']} stream entries | {case['title']}")
    print('Redis', result['version'], '| receipt', result['sha256'])


if __name__ == '__main__':
    main()
