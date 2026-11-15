"""Opt-in integration tests; only scratch IDs 720000..720300 are modified."""
import os
import unittest

from hydra import Hydra, HydraError
from app.config import connect


@unittest.skipUnless(os.getenv('AFTERTRACE_LIVE_TEST') == '1', 'set AFTERTRACE_LIVE_TEST=1 for real HydraDB tests')
class LiveTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = connect()

    def test_auth_and_syntax_fail_closed(self):
        bad = Hydra(os.environ['HYDRA_URL'], 'incorrect-token-that-is-at-least-32-characters')
        with self.assertRaisesRegex(HydraError, '401'):
            bad.query('MATCH (n {id: 720000}) RETURN n.id AS id')
        with self.assertRaises(HydraError):
            self.client.query('THIS IS NOT CYPHER')

    def test_real_pagination_and_repeatable_merge(self):
        ids = [{'id': n} for n in range(720000, 720301)]
        cleanup = 'UNWIND $rows AS row MATCH (n {id: row.id}) DETACH DELETE n'
        self.client.query(cleanup, {'rows': ids})
        try:
            nodes = [{'id': n, 'name': str(n)} for n in range(720000, 720301)]
            self.client.query('UNWIND $rows AS row MERGE (n {id: row.id}) SET n:AftertraceTransportSmoke, n.name = row.name', {'rows': nodes})
            rows = self.client.query('MATCH (n:AftertraceTransportSmoke) RETURN n.id AS id ORDER BY id')
            self.assertEqual([r['id'] for r in rows], list(range(720000, 720301)))
            for _ in range(2):
                self.client.query('MERGE (a {id: $src})-[:TRANSPORT_SMOKE]->(b {id: $dst})', {'src': 720000, 'dst': 720001})
            rows = self.client.query('MATCH (a {id: $src})-[:TRANSPORT_SMOKE]->(b) RETURN b.id AS id', {'src': 720000})
            self.assertEqual(rows, [{'id': 720001}])
            rows = self.client.query('MATCH (n {id: $id}) RETURN n.missing AS absent', {'id': 720000})
            self.assertEqual(rows, [{'absent': None}])
            rows = self.client.query('MATCH (a {id: $src})-[:TRANSPORT_SMOKE]->(b) RETURN collect(b.id) AS ids', {'src': 720000})
            self.assertEqual(rows, [{'ids': [720001]}])
        finally:
            self.client.query(cleanup, {'rows': ids})
