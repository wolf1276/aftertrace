import os
import unittest
import uuid
from unittest.mock import Mock, patch

import duckdb

from app.graph import ContextGraph, GraphError, RELATIONS, catalog, identity
from app.config import connect


def schema_db():
    db = duckdb.connect(':memory:')
    columns = 'event_id VARCHAR, shipment_id INTEGER, source VARCHAR, status VARCHAR, fee_cents INTEGER, event_day INTEGER'
    for table in RELATIONS:
        db.execute(f'CREATE TABLE {table} ({columns})')
    return db


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = schema_db()
        self.addCleanup(self.db.close)

    def test_introspected_schema_and_declared_lineage(self):
        nodes, edges = catalog(self.db)
        fields = [n for n in nodes if n['kind'] == 'Field']
        self.assertEqual(len(fields), 30)
        self.assertIn('INTEGER', next(n['detail'] for n in fields if n['name'] == 'shipment_facts.fee_cents'))
        self.assertIn(('Field:shipment_facts.fee_cents', 'DERIVES', 'Field:delivery_fee_kpi.fee_cents'), edges)
        self.assertEqual(len(edges), len(set(edges)))
        self.assertNotIn('root_cause', str(nodes))
        self.assertNotIn('duplicate_heldout', str(nodes))

    def test_identity_and_inputs(self):
        self.assertEqual(identity('abc'), identity('abc'))
        self.assertNotEqual(identity('abc'), identity('abd'))
        self.assertNotEqual(ContextGraph(Mock(), 'one')._id('x'), ContextGraph(Mock(), 'two')._id('x'))
        for kwargs in ({'scope': ''}, {'scope': 1}, {'max_nodes': 0}, {'max_nodes': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ContextGraph(Mock(), **kwargs)
        graph = ContextGraph(Mock())
        for hops in (0, 5, True, '3'):
            with self.assertRaises(ValueError):
                graph.upstream(max_hops=hops)

    def test_missing_manifest_and_collision_fail_closed(self):
        client = Mock()
        graph = ContextGraph(client)
        with patch.object(graph, '_manifest', return_value=[]):
            with self.assertRaises(GraphError):
                graph.context()
            client.query.return_value = [{'key': 'someone-else'}]
            with self.assertRaisesRegex(GraphError, 'collision'):
                graph.seed(self.db)
        self.assertTrue(all('MATCH' in c.args[0] for c in client.query.call_args_list))

    def test_budget_before_any_write(self):
        client = Mock()
        with self.assertRaisesRegex(GraphError, 'budget'):
            ContextGraph(client, max_nodes=2).seed(self.db)
        client.query.assert_not_called()


@unittest.skipUnless(os.getenv('AFTERTRACE_LIVE_TEST') == '1', 'requires real HydraDB')
class LiveGraphTests(unittest.TestCase):
    def setUp(self):
        self.client = connect()
        self.graph = ContextGraph(self.client, 'graph-test-' + uuid.uuid4().hex)
        self.db = schema_db()
        self.addCleanup(self.db.close)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        nodes, _ = catalog(self.db)
        rows = [{'id': self.graph._id(n['key'])} for n in nodes] + [{'id': self.graph.manifest_id}]
        self.client.query('UNWIND $rows AS row MATCH (n {id: row.id}) DETACH DELETE n', {'rows': rows})

    def test_repeatable_ingestion_retrieval_and_scope_isolation(self):
        first = self.graph.seed(self.db)
        second = self.graph.seed(self.db)
        self.assertEqual(first, second)
        self.assertEqual(first['source'], 'hydradb')
        self.assertEqual(len(first['nodes']), len(catalog(self.db)[0]))
        self.assertEqual(len(first['edges']), len(catalog(self.db)[1]))
        context = self.graph.field_context('delivery_fee_kpi.fee_cents')
        self.assertEqual([n['depth'] for n in context['upstream']], [1, 1, 2, 2, 3, 3])
        self.assertEqual({n['name'] for n in context['upstream']}, {f'{table}.{field}' for table in ('shipment_facts', 'normalized_events', 'delivery_events') for field in ('fee_cents', 'event_id')})
        self.assertIn('fee_reconciliation', [t['name'] for t in context['tools']])
        self.assertIn('duplicate_profile', [t['name'] for t in context['tools']])
        self.assertTrue(context['contracts'])
        self.assertEqual(len(self.graph.search('shipment')), 1)
        with self.assertRaises(GraphError):
            ContextGraph(self.client, 'not-ingested-' + uuid.uuid4().hex).context()
        with self.assertRaises(GraphError):
            self.graph.field_context('not_a_real_field')
        self.assertEqual(self.graph.upstream('carrier_heartbeats.event_day'), [])
        with self.assertRaisesRegex(GraphError, 'budget'):
            self.graph.upstream(limit=1)

    def test_partial_write_recovery_and_schema_drift(self):
        real_query = self.client.query
        failed = False

        def query(text, parameters=None):
            nonlocal failed
            if 'CREATE (a' in text and not failed:
                failed = True
                raise RuntimeError('injected edge-write failure')
            return real_query(text, parameters)

        with patch.object(self.client, 'query', side_effect=query):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.graph.seed(self.db)
        with self.assertRaisesRegex(GraphError, 'not ready'):
            self.graph.context()
        self.assertTrue(self.graph.seed(self.db)['nodes'])
        self.db.execute('ALTER TABLE delivery_events ADD COLUMN extra VARCHAR')
        with self.assertRaisesRegex(GraphError, 'schema changed'):
            self.graph.seed(self.db)
        self.db.execute('ALTER TABLE delivery_events DROP COLUMN extra')

    def test_cycles_are_bounded_and_do_not_return_self(self):
        self.graph.seed(self.db)
        self.client.query('MERGE (a {id: $a})-[:DERIVES]->(b {id: $b})', {
            'a': self.graph._id('Field:delivery_fee_kpi.fee_cents'),
            'b': self.graph._id('Field:delivery_events.fee_cents')})
        result = self.graph.upstream(max_hops=4)
        self.assertEqual(len(result), 6)
        self.assertNotIn('delivery_fee_kpi.fee_cents', [n['name'] for n in result])


if __name__ == '__main__':
    unittest.main()
