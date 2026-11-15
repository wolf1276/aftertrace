import json
import unittest

from app.fixture import (BROKEN, EVENT_COLUMNS, FIXED, VERSION, VERSIONS,
                         measure, profile, verify, warehouse)

BAD_FILTER = "SELECT * FROM normalized_events WHERE source = 'carrier_a'"


class FixtureTests(unittest.TestCase):
    def open(self, *args, **kwargs):
        db = warehouse(*args, **kwargs)
        self.addCleanup(db.close)
        return db

    def failed(self, checks):
        return {check['name'] for check in checks if not check['passed']}

    def facts(self, db):
        return db.execute(
            'SELECT event_id, shipment_id, source, status, fee_cents, event_day '
            'FROM shipment_facts ORDER BY event_id').fetchall()

    def test_input_validation(self):
        for scenario in ('unknown', '', None):
            with self.assertRaises(ValueError):
                warehouse(scenario, 1)
        for seed in (True, False, 0, 10001, -1, 1.0, '1', None):
            with self.assertRaises(ValueError):
                warehouse('healthy', seed)
        for transform in ('', '   ', None, 1):
            with self.assertRaises(ValueError):
                warehouse('healthy', 1, transform)
        self.open('healthy', 1)
        self.open('healthy', 10000)
        self.open('duplicate_heldout', 10000)

    def test_versions_are_declared(self):
        self.assertIsInstance(VERSION, str)
        self.assertEqual(VERSIONS['fixture'], VERSION)
        self.assertTrue(all(isinstance(value, str) and value for value in VERSIONS.values()))

    def test_relations_and_schema(self):
        db = self.open('duplicate', 1)
        relations = {row[0] for row in db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
        for relation in ('delivery_events', 'normalized_events', 'shipment_facts',
                         'delivery_fee_kpi', 'carrier_heartbeats'):
            self.assertIn(relation, relations)
        columns = [row[0] for row in db.execute(
            'SELECT column_name FROM information_schema.columns '
            "WHERE table_name = 'delivery_events' ORDER BY ordinal_position").fetchall()]
        self.assertEqual(columns, list(EVENT_COLUMNS))
        kpi_columns = {row[0] for row in db.execute(
            'SELECT column_name FROM information_schema.columns '
            "WHERE table_name = 'delivery_fee_kpi'").fetchall()}
        self.assertTrue({'event_day', 'fee_cents'} <= kpi_columns)

    def test_healthy_passes(self):
        m, checks = profile('healthy', 1)
        self.assertTrue(all(check['passed'] for check in checks), self.failed(checks))
        self.assertEqual(m['rows'], 100)
        self.assertEqual(m['unique_events'], 100)
        self.assertEqual(m['unique_shipments'], 100)
        self.assertEqual(m['duplicate_rows'], 0)
        self.assertEqual(m['null_rate'], 0.0)
        self.assertEqual(m['reconciliation']['difference'], 0)
        self.assertEqual(m['heartbeats']['stale_sources'], [])

    def test_measurements_are_deterministic(self):
        first = profile('duplicate', 7)
        second = profile('duplicate', 7)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        a = measure(self.open('duplicate', 7))
        b = measure(self.open('duplicate', 7))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_duplicate_default_transform_fails(self):
        m, checks = profile('duplicate', 3)
        failed = self.failed(checks)
        for name in ('event uniqueness', 'fee reconciliation', 'accepted event accounting',
                     'carrier partition conservation'):
            self.assertIn(name, failed)
        self.assertGreater(m['duplicate_rows'], 0)
        self.assertGreater(m['reconciliation']['difference'], 0)
        self.assertGreater(m['reconciliation']['inflation'], 0)

    def test_duplicate_fixed_restores_invariants(self):
        for seed in (1, 2, 7, 100, 10000):
            with self.subTest(seed=seed):
                db = self.open('duplicate', seed, FIXED)
                checks = verify(db, seed)
                self.assertTrue(all(check['passed'] for check in checks), self.failed(checks))
                m = measure(db)
                self.assertEqual(m['rows'], 100)
                self.assertEqual(m['unique_events'], 100)
                self.assertEqual(m['unique_shipments'], 100)
                self.assertEqual(m['duplicate_rows'], 0)
                self.assertEqual(m['reconciliation']['difference'], 0)

    def test_conservation_and_unaffected_partitions(self):
        broken = self.open('duplicate', 11)
        fixed = self.open('duplicate', 11, FIXED)
        healthy = self.open('healthy', 11)
        replayed = broken.execute(
            'SELECT count(*) FROM (SELECT event_id, shipment_id, source, status, fee_cents, '
            'event_day, count(*) AS copies FROM delivery_events GROUP BY ALL HAVING copies > 1)'
        ).fetchone()[0]
        self.assertGreater(replayed, 0)
        self.assertEqual(broken.execute(
            'SELECT count(DISTINCT event_id) FROM delivery_events').fetchone()[0], 100)
        self.assertEqual(self.facts(fixed), self.facts(healthy))
        for carrier in ('carrier_a', 'carrier_b'):
            query = f"SELECT count(*) FROM shipment_facts WHERE source = '{carrier}'"
            self.assertEqual(fixed.execute(query).fetchone()[0],
                             healthy.execute(query).fetchone()[0])
        self.assertEqual(broken.execute(
            "SELECT count(*) - count(DISTINCT event_id) FROM delivery_events "
            "WHERE source = 'carrier_a'").fetchone()[0], 0)

    def test_bad_filtering_repair_fails(self):
        db = self.open('duplicate', 5, BAD_FILTER)
        failed = self.failed(verify(db, 5))
        self.assertNotIn('event uniqueness', failed)
        for name in ('shipment completeness', 'fee reconciliation', 'source coverage',
                     'accepted event accounting', 'carrier partition conservation'):
            self.assertIn(name, failed)

    def test_stale_fails_even_after_dedupe(self):
        for transform in (BROKEN, FIXED):
            with self.subTest(transform=transform):
                db = self.open('stale', 4, transform)
                m = measure(db)
                failed = self.failed(verify(db, 4))
                self.assertIn('shipment completeness', failed)
                self.assertLess(m['unique_shipments'], 100)
                if transform == FIXED:
                    self.assertNotIn('event uniqueness', failed)
                    self.assertNotIn('accepted event accounting', failed)
        self.assertTrue(all(check['passed'] for check in verify(
            self.open('healthy', 4), 4)))

    def test_heldout_variants(self):
        for seed in (1, 2, 7, 100, 10000):
            with self.subTest(seed=seed):
                db = self.open('duplicate_heldout', seed, FIXED)
                checks = verify(db, seed)
                self.assertTrue(all(check['passed'] for check in checks), self.failed(checks))
        failed = self.failed(verify(self.open('duplicate_heldout', 2), 2))
        for name in ('event uniqueness', 'fee reconciliation', 'carrier partition conservation'):
            self.assertIn(name, failed)
        trained = self.open('duplicate', 2)
        held = self.open('duplicate_heldout', 2)
        self.assertNotEqual(
            {row[0] for row in trained.execute('SELECT DISTINCT source FROM delivery_events').fetchall()},
            {row[0] for row in held.execute('SELECT DISTINCT source FROM delivery_events').fetchall()})
        self.assertTrue(held.execute('SELECT min(event_id) FROM delivery_events').fetchone()[0]
                        .startswith('evt-h-'))
        self.assertFalse(trained.execute('SELECT min(event_id) FROM delivery_events').fetchone()[0]
                         .startswith('evt-h-'))

    def test_distractor_heartbeats_cannot_explain_fees(self):
        db = self.open('duplicate', 6)
        m = measure(db)
        self.assertEqual(m['heartbeats']['stale_sources'], ['carrier_a'])
        self.assertEqual(db.execute(
            'SELECT count(*) FROM carrier_heartbeats WHERE critical').fetchone()[0], 0)
        by_source = {row['source']: row for row in m['by_source']}
        self.assertEqual(by_source['carrier_a']['duplicates'], 0)
        self.assertGreater(by_source['carrier_b']['duplicates'], 0)
        raw = db.execute('SELECT sum(fee_cents) FROM delivery_events').fetchone()[0]
        accepted = db.execute(
            'SELECT sum(fee_cents) FROM (SELECT fee_cents FROM delivery_events '
            'QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY event_day) = 1)'
        ).fetchone()[0]
        self.assertGreater(m['reconciliation']['inflation'], 0)
        self.assertEqual(m['reconciliation']['inflation'], raw - accepted)
        healthy, _ = profile('healthy', 6)
        self.assertEqual(healthy['heartbeats']['stale_sources'], [])

    def test_measure_is_diagnostic(self):
        m = measure(self.open('duplicate', 1))
        for key in ('daily_history', 'duplicate_rate', 'null_rate', 'reconciliation',
                    'by_source', 'heartbeats'):
            self.assertIn(key, m)
        self.assertEqual(sum(row['fee_cents'] for row in m['daily_history']), m['fee_cents'])
        self.assertEqual(m['reconciliation']['fact_fee_cents'], m['fee_cents'])
        self.assertIsInstance(m['duplicate_rate'], float)
        self.assertIsInstance(m['null_rate'], float)
        self.assertTrue(all(row['duplicates'] >= 0 for row in m['by_source']))

    def test_relabeling_events_cannot_pass_by_preserving_totals(self):
        transform = "SELECT 'renamed-' || event_id AS event_id, shipment_id, source, status, fee_cents, event_day FROM normalized_events"
        db = self.open('healthy', 1, transform)
        failed = self.failed(verify(db, 1))
        self.assertIn('accepted event content conservation', failed)
        self.assertNotIn('fee reconciliation', failed)

    def test_null_required_values_are_rejected(self):
        transform = 'SELECT event_id, shipment_id, NULL::VARCHAR AS source, status, fee_cents, event_day FROM normalized_events'
        db = self.open('healthy', 1, transform)
        self.assertIn('non-null required values', self.failed(verify(db, 1)))

    def test_seed_changes_fees_not_shape(self):
        first = measure(self.open('healthy', 1))
        second = measure(self.open('healthy', 2))
        self.assertNotEqual(first['fee_cents'], second['fee_cents'])
        self.assertEqual(first['unique_shipments'], second['unique_shipments'])

    def test_failed_transform_does_not_leak_connection(self):
        with self.assertRaises(Exception):
            warehouse('duplicate', 1, 'SELECT * FROM missing_relation')
        m, checks = profile('healthy', 1)
        self.assertTrue(all(check['passed'] for check in checks))


if __name__ == '__main__':
    unittest.main()
