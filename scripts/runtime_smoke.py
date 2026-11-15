#!/usr/bin/env python3
"""Live HydraDB runtime smoke test. Prints JSON receipts, never the token."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import connect  # noqa: E402

SCRATCH = (880000001, 880000002, 880000003)
SCRATCH_REL = 'PHASE1_SMOKE'
SCRATCH_MARKER = 'aftertrace-phase1-smoke'
PERSIST = (880000900, 880000901)
PERSIST_REL = 'PHASE1_PERSIST'
PERSIST_MARKER = 'aftertrace-phase1-persistence'


class Receipt:
    def __init__(self, mode):
        self.mode = mode
        self.operations = []
        self.checks = []
        self.started = time.perf_counter()

    def op(self, name):
        self.operations.append(name)

    def check(self, name, condition, detail):
        self.checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(f'{name}: {detail}')

    def emit(self, error=None):
        receipt = {
            'mode': self.mode,
            'ok': error is None,
            'elapsed_seconds': round(time.perf_counter() - self.started, 3),
            'operations': self.operations,
            'checks': self.checks,
        }
        if error is not None:
            receipt['error'] = error
        print(json.dumps(receipt, sort_keys=True))


def safe_error(exc, secret=None):
    text = f'{type(exc).__name__}: {exc}'
    return text.replace(secret, '<redacted>') if secret else text


def cleanup_ids(client, receipt, ids, marker, label):
    for node_id in ids:
        client.query('MATCH (n {id: $id}) WHERE n.marker = $marker DETACH DELETE n',
                     {'id': node_id, 'marker': marker})
    receipt.op(f'cleanup:{label}')
    remaining = []
    for node_id in ids:
        rows = client.query('MATCH (n {id: $id}) RETURN count(*) AS total', {'id': node_id})
        remaining.append(rows[0]['total'] if rows else None)
    receipt.check(f'{label} cleaned', remaining == [0] * len(ids), remaining)


def run_smoke(client, receipt):
    src, dst, other = SCRATCH
    merge = f'MERGE (a {{id: $src, marker: $marker}})-[:{SCRATCH_REL}]->(b {{id: $dst, marker: $marker}})'
    for target in (dst, other):
        for _ in range(2):
            client.query(merge, {'src': src, 'dst': target, 'marker': SCRATCH_MARKER})
    receipt.op('merge:idempotent_edges')

    rows = client.query(f'MATCH (a {{id: $src}})-[:{SCRATCH_REL}]->(b {{id: $dst}}) RETURN b.id AS id',
                        {'src': src, 'dst': dst})
    receipt.check('vertex_id exact', rows == [{'id': dst}], rows)

    rows = client.query(f'MATCH (a {{id: $src}})-[:{SCRATCH_REL}]->(b) RETURN count(*) AS total',
                        {'src': src})
    receipt.check('merge idempotent', rows == [{'total': 2}], rows)

    rows = client.query(f'MATCH (a {{id: $src}})-[:{SCRATCH_REL}]->(b) RETURN collect(b.id) AS ids',
                        {'src': src})
    receipt.check('list decoding exact', rows and sorted(rows[0]['ids']) == [dst, other], rows)

    rows = client.query(f'MATCH (a {{id: $src}}) OPTIONAL MATCH (a)-[:NO_SUCH_PHASE1_EDGE]->(b) RETURN b.id AS id',
                        {'src': src})
    receipt.check('null decoding exact', rows == [{'id': None}], rows)

    rows = client.query('MATCH (a {id: $src}) RETURN a.id AS id, a.marker AS marker', {'src': src})
    receipt.check('property exact', rows == [{'id': src, 'marker': SCRATCH_MARKER}], rows)
    receipt.op('read:vertex_id_null_list_property')


def write_persistence(client, receipt):
    src, dst = PERSIST
    merge = f'MERGE (a {{id: $src, marker: $marker}})-[:{PERSIST_REL}]->(b {{id: $dst, marker: $marker}})'
    for _ in range(2):
        client.query(merge, {'src': src, 'dst': dst, 'marker': PERSIST_MARKER})
    receipt.op('merge:persistence_marker')
    rows = client.query(f'MATCH (a {{id: $src}})-[:{PERSIST_REL}]->(b {{id: $dst}}) '
                        'RETURN a.id AS src, b.id AS dst, a.marker AS marker', {'src': src, 'dst': dst})
    receipt.check('persistence marker write', rows == [{'src': src, 'dst': dst, 'marker': PERSIST_MARKER}], rows)
    rows = client.query(f'MATCH (a {{id: $src}})-[:{PERSIST_REL}]->(b) RETURN count(*) AS total', {'src': src})
    receipt.check('persistence marker idempotent', rows == [{'total': 1}], rows)


def check_persistence(client, receipt):
    src, dst = PERSIST
    rows = client.query(f'MATCH (a {{id: $src}})-[:{PERSIST_REL}]->(b {{id: $dst}}) '
                        'RETURN a.id AS src, b.id AS dst, a.marker AS marker, b.marker AS dst_marker',
                        {'src': src, 'dst': dst})
    expected = [{'src': src, 'dst': dst, 'marker': PERSIST_MARKER, 'dst_marker': PERSIST_MARKER}]
    receipt.op('read:persistence_marker')
    receipt.check('persistence marker readable', rows == expected, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--write-persistence', action='store_true',
                       help='write the restart-persistence marker')
    modes.add_argument('--check-persistence', action='store_true',
                       help='read the marker written before a restart')
    modes.add_argument('--cleanup-persistence', action='store_true',
                       help='delete only the persistence marker ids')
    args = parser.parse_args(argv)

    mode = ('write-persistence' if args.write_persistence else
            'check-persistence' if args.check_persistence else
            'cleanup-persistence' if args.cleanup_persistence else 'smoke')
    receipt = Receipt(mode)
    client = None
    error = None
    try:
        client = connect()
        if args.write_persistence:
            write_persistence(client, receipt)
        elif args.check_persistence:
            check_persistence(client, receipt)
        elif args.cleanup_persistence:
            cleanup_ids(client, receipt, PERSIST, PERSIST_MARKER, 'persistence marker')
        else:
            run_smoke(client, receipt)
    except Exception as exc:
        error = safe_error(exc, getattr(client, 'token', None))
    finally:
        if mode == 'smoke' and client is not None:
            try:
                cleanup_ids(client, receipt, SCRATCH, SCRATCH_MARKER, 'scratch')
            except Exception as exc:
                if error is None:
                    error = safe_error(exc, getattr(client, 'token', None))
                else:
                    receipt.checks.append({'name': 'scratch cleanup', 'passed': False})
    receipt.emit(error)
    return 1 if error else 0


if __name__ == '__main__':
    sys.exit(main())
