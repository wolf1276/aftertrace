"""Deterministic synthetic fulfillment fixture. No production data.

Pipeline: delivery_events (raw) -> normalized_events -> shipment_facts -> delivery_fee_kpi.
Scenario labels and expected answers never appear in warehouse tables.
"""
import duckdb

VERSION = 'fulfillment-v2'
GENERATOR_VERSION = 'generator-v2'
CONTRACT_VERSION = 'contract-v2'
TRANSFORM_VERSION = 'transform-v2'
INVARIANT_VERSION = 'invariants-v2.1'
VERSIONS = {
    'fixture': VERSION,
    'generator': GENERATOR_VERSION,
    'contract': CONTRACT_VERSION,
    'transform': TRANSFORM_VERSION,
    'invariants': INVARIANT_VERSION,
}

SCENARIOS = ('duplicate', 'healthy', 'stale', 'duplicate_heldout')
SHIPMENTS = 100
DUPLICATE_REPLAYS = 2
EVENT_COLUMNS = ('event_id', 'shipment_id', 'source', 'status', 'fee_cents', 'event_day')

BROKEN = 'SELECT * FROM normalized_events'
FIXED = '''SELECT event_id, shipment_id, source, status, fee_cents, event_day
FROM normalized_events
QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY event_day) = 1'''


def _validate_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, int) or not 1 <= seed <= 10000:
        raise ValueError(f'Seed must be an integer in [1, 10000], got {seed!r}')


def _validate(scenario, seed, transform):
    if scenario not in SCENARIOS:
        raise ValueError(f'Unknown scenario: {scenario!r}')
    _validate_seed(seed)
    if not isinstance(transform, str) or not transform.strip():
        raise ValueError('Transform must be a non-empty SQL string')


def _source_partitions(scenario):
    # Held-out uses different source partitions than the training scenarios.
    if scenario == 'duplicate_heldout':
        return {0: 'carrier_c', 1: 'carrier_d'}
    return {0: 'carrier_a', 1: 'carrier_b'}


def _event_prefix(scenario):
    return 'evt-h' if scenario == 'duplicate_heldout' else 'evt'


def _events(seed, scenario):
    sources = _source_partitions(scenario)
    prefix = _event_prefix(scenario)
    return [(f'{prefix}-{seed}-{shipment}', shipment, sources[shipment % 2], 'delivered',
             400 + ((shipment * 17 + seed) % 300), 1 + shipment // 10)
            for shipment in range(1, SHIPMENTS + 1)]


def _scenario_events(seed, scenario):
    rows = _events(seed, scenario)
    if scenario == 'stale':
        return [row for row in rows if row[5] < 9]
    if scenario in ('duplicate', 'duplicate_heldout'):
        target = _source_partitions(scenario)[1]
        replayed = [row for row in rows if row[2] == target][:20 + seed % 10]
        return rows + replayed * DUPLICATE_REPLAYS
    return rows


def _heartbeats(seed, scenario):
    sources = sorted(set(_source_partitions(scenario).values()))
    stale_source = _source_partitions(scenario)[0]
    distractor = scenario in ('duplicate', 'duplicate_heldout')
    rows = []
    for source in sources:
        for day in range(1, 12):
            if distractor and source == stale_source and day >= 5:
                continue
            rows.append((source, day, 10 + (day * 7 + seed) % 5,
                         5 + (day * 3 + seed) % 20, False))
    return rows


def warehouse(scenario='duplicate', seed=1, transform=BROKEN):
    _validate(scenario, seed, transform)
    db = duckdb.connect(':memory:')
    try:
        db.execute('CREATE TABLE delivery_events(event_id VARCHAR, shipment_id INTEGER, '
                   'source VARCHAR, status VARCHAR, fee_cents INTEGER, event_day INTEGER)')
        db.executemany('INSERT INTO delivery_events VALUES (?, ?, ?, ?, ?, ?)',
                       _scenario_events(seed, scenario))
        db.execute('CREATE TABLE carrier_heartbeats(source VARCHAR, event_day INTEGER, '
                   'heartbeat_count INTEGER, lag_seconds INTEGER, critical BOOLEAN)')
        db.executemany('INSERT INTO carrier_heartbeats VALUES (?, ?, ?, ?, ?)',
                       _heartbeats(seed, scenario))
        db.execute('CREATE VIEW normalized_events AS '
                   'SELECT event_id, CAST(shipment_id AS INTEGER) AS shipment_id, '
                   'lower(source) AS source, lower(status) AS status, '
                   'CAST(fee_cents AS INTEGER) AS fee_cents, CAST(event_day AS INTEGER) AS event_day '
                   'FROM delivery_events')
        db.execute('CREATE VIEW shipment_facts AS ' + transform)
        db.execute('CREATE VIEW delivery_fee_kpi AS '
                   'SELECT event_day, sum(fee_cents) AS fee_cents, count(*) AS shipments, '
                   'count(DISTINCT event_id) AS events '
                   'FROM shipment_facts GROUP BY event_day')
        return db
    except Exception:
        db.close()
        raise


def _one(db, sql):
    return db.execute(sql).fetchone()[0]


def measure(db):
    rows, unique_events, unique_shipments, fees = db.execute(
        'SELECT count(*), count(DISTINCT event_id), count(DISTINCT shipment_id), '
        'coalesce(sum(fee_cents), 0) FROM shipment_facts').fetchone()
    raw_rows, raw_unique_events, raw_fees = db.execute(
        'SELECT count(*), count(DISTINCT event_id), coalesce(sum(fee_cents), 0) '
        'FROM delivery_events').fetchone()
    accepted_fees = _one(db, 'SELECT coalesce(sum(fee_cents), 0) FROM ('
                             'SELECT fee_cents FROM delivery_events '
                             'QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY event_day) = 1)')
    null_event_ids = _one(db, 'SELECT count(*) FROM shipment_facts WHERE event_id IS NULL')
    null_shipment_ids = _one(db, 'SELECT count(*) FROM shipment_facts WHERE shipment_id IS NULL')
    null_fees = _one(db, 'SELECT count(*) FROM shipment_facts WHERE fee_cents IS NULL')
    duplicate_rows = rows - unique_events
    raw_duplicate_rows = raw_rows - raw_unique_events

    by_source = []
    for source, source_rows, source_events in db.execute(
            'SELECT source, count(*), count(DISTINCT event_id) FROM delivery_events '
            'GROUP BY source ORDER BY source').fetchall():
        by_source.append({'source': source, 'rows': source_rows,
                          'unique_events': source_events,
                          'duplicates': source_rows - source_events})

    daily_history = [{'event_day': day, 'fee_cents': fee, 'shipments': shipments, 'events': events}
                     for day, fee, shipments, events in db.execute(
                         'SELECT event_day, fee_cents, shipments, events '
                         'FROM delivery_fee_kpi ORDER BY event_day').fetchall()]

    heartbeat_sources = [{'source': source, 'last_day': last_day, 'days': days,
                          'critical': bool(critical)}
                         for source, last_day, days, critical in db.execute(
                             'SELECT source, max(event_day), count(*), bool_or(critical) '
                             'FROM carrier_heartbeats GROUP BY source ORDER BY source').fetchall()]
    overall_last_day = _one(db, 'SELECT coalesce(max(event_day), 0) FROM carrier_heartbeats')
    stale_sources = [h['source'] for h in heartbeat_sources if h['last_day'] < overall_last_day]

    return {
        'rows': rows,
        'unique_events': unique_events,
        'unique_shipments': unique_shipments,
        'fee_cents': fees,
        'duplicate_rows': duplicate_rows,
        'duplicate_rate': duplicate_rows / rows if rows else 0.0,
        'null_event_ids': null_event_ids,
        'null_shipment_ids': null_shipment_ids,
        'null_fees': null_fees,
        'null_rate': (null_event_ids + null_shipment_ids + null_fees) / (3 * rows) if rows else 0.0,
        'raw_rows': raw_rows,
        'raw_unique_events': raw_unique_events,
        'raw_duplicate_rows': raw_duplicate_rows,
        'raw_duplicate_rate': raw_duplicate_rows / raw_rows if raw_rows else 0.0,
        'reconciliation': {
            'raw_fee_cents': raw_fees,
            'accepted_fee_cents': accepted_fees,
            'fact_fee_cents': fees,
            'difference': fees - accepted_fees,
            'inflation': raw_fees - accepted_fees,
        },
        'daily_history': daily_history,
        'by_source': by_source,
        'heartbeats': {
            'sources': heartbeat_sources,
            'stale_sources': stale_sources,
            'max_lag_seconds': _one(db, 'SELECT coalesce(max(lag_seconds), 0) FROM carrier_heartbeats'),
        },
    }


def verify(db, seed):
    _validate_seed(seed)
    m = measure(db)
    canonical = _events(seed, 'healthy')
    expected_fee = sum(row[4] for row in canonical)
    expected_shipments = len({row[1] for row in canonical})
    raw_sources = _one(db, 'SELECT count(DISTINCT source) FROM delivery_events')
    accepted_by_source = dict(db.execute(
        'SELECT source, count(DISTINCT event_id) FROM delivery_events '
        'GROUP BY source ORDER BY source').fetchall())
    fact_by_source = dict(db.execute(
        'SELECT source, count(*) FROM shipment_facts GROUP BY source ORDER BY source').fetchall())
    checks = [
        ('event uniqueness', m['rows'] == m['unique_events'] and m['duplicate_rows'] == 0),
        ('shipment completeness', m['unique_shipments'] == expected_shipments),
        ('fee reconciliation', m['fee_cents'] == expected_fee),
        ('source coverage', len(fact_by_source) == raw_sources
         and all(count > 0 for count in fact_by_source.values())),
        ('non-null event identity', m['null_event_ids'] == 0),
        ('one delivery per shipment', m['rows'] == m['unique_shipments']),
        ('positive fees', _one(db, 'SELECT count(*) FROM shipment_facts WHERE fee_cents <= 0') == 0),
        ('accepted event accounting',
         m['rows'] == _one(db, 'SELECT count(DISTINCT event_id) FROM delivery_events')),
        ('carrier partition conservation', fact_by_source == accepted_by_source),
        ('non-null required values', _one(db, 'SELECT count(*) FROM shipment_facts WHERE '
         'event_id IS NULL OR shipment_id IS NULL OR source IS NULL OR status IS NULL '
         'OR fee_cents IS NULL OR event_day IS NULL') == 0),
        ('accepted event content conservation',
         set(db.execute('SELECT DISTINCT ' + ', '.join(EVENT_COLUMNS) + ' FROM normalized_events').fetchall())
         == set(db.execute('SELECT DISTINCT ' + ', '.join(EVENT_COLUMNS) + ' FROM shipment_facts').fetchall())),
    ]
    return [{'name': name, 'passed': bool(ok)} for name, ok in checks]


def profile(scenario, seed):
    db = warehouse(scenario, seed)
    try:
        return measure(db), verify(db, seed)
    finally:
        db.close()
