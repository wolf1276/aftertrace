"""HydraDB context catalog. Only app-owned IDs, parameter values, and bounded reads."""
import hashlib
import json

from app.fixture import CONTRACT_VERSION, VERSION, warehouse

RELATIONS = ('delivery_events', 'normalized_events', 'shipment_facts', 'delivery_fee_kpi', 'carrier_heartbeats')
LABELS = ('Dataset', 'Field', 'Contract', 'Tool')
EDGE_LABELS = {'FEEDS': 'Dataset', 'HAS_FIELD': 'Dataset', 'DERIVES': 'Field',
               'GOVERNED_BY': 'Field', 'INSPECTS': 'Tool'}
TOOLS = {
    'duplicate_profile': ('delivery_events.event_id', 'shipment_facts.event_id'),
    'fee_reconciliation': ('delivery_events.fee_cents', 'shipment_facts.fee_cents', 'delivery_fee_kpi.fee_cents'),
    'completeness_profile': ('delivery_events.shipment_id', 'shipment_facts.shipment_id'),
    'freshness_profile': ('carrier_heartbeats.event_day',),
}


class GraphError(RuntimeError):
    pass


def identity(key):
    return 10**12 + int(hashlib.sha256(key.encode()).hexdigest()[:13], 16)


def catalog(db):
    """Introspect real schemas; declared lineage describes our owned fixture SQL."""
    nodes, edges = [], []

    def node(kind, name, layer='', detail=''):
        key = kind + ':' + name
        nodes.append({'key': key, 'kind': kind, 'name': name, 'layer': layer, 'detail': detail})
        return key

    fields = {}
    for table in RELATIONS:
        dataset = node('Dataset', table, 'raw' if table in ('delivery_events', 'carrier_heartbeats') else 'metric' if table == 'delivery_fee_kpi' else 'model')
        # Identifiers come exclusively from RELATIONS, never user text.
        fields[table] = {}
        for name, data_type, nullable, *_ in db.execute('DESCRIBE ' + table).fetchall():
            field = node('Field', table + '.' + name, table, json.dumps({'type': data_type, 'nullable': nullable == 'YES'}, sort_keys=True))
            fields[table][name] = field
            edges.append((dataset, 'HAS_FIELD', field))
    for source, target in zip(RELATIONS[:3], RELATIONS[1:4]):
        edges.append(('Dataset:' + source, 'FEEDS', 'Dataset:' + target))
        for name in sorted(fields[source].keys() & fields[target].keys()):
            edges.append((fields[source][name], 'DERIVES', fields[target][name]))
    # Aggregate cardinality depends on canonical event identity as well as fee values.
    if 'fee_cents' in fields['delivery_fee_kpi']:
        edges.append((fields['shipment_facts']['event_id'], 'DERIVES', fields['delivery_fee_kpi']['fee_cents']))
    for table, columns in fields.items():
        for name, field in columns.items():
            if name not in ('event_id', 'shipment_id', 'fee_cents'):
                continue
            meaning = {
                'event_id': 'Stable event identity. Canonical records contain one row per accepted event identity.',
                'shipment_id': 'Shipment identifier. All accepted shipments must be retained through normalization.',
                'fee_cents': 'Delivery fee in integer cents. Aggregate fees reconcile to canonical accepted delivery events.',
            }[name]
            contract = node('Contract', table + '.' + name, CONTRACT_VERSION, meaning)
            edges.append((field, 'GOVERNED_BY', contract))
    for name, targets in TOOLS.items():
        tool = node('Tool', name, 'read-only', json.dumps({'operation': name, 'input': {'dataset': 'string'}, 'version': 'v1'}, sort_keys=True))
        for target in targets:
            table, field = target.split('.')
            if field in fields[table]:
                edges.append((tool, 'INSPECTS', fields[table][field]))
    return nodes, sorted(set(edges))


class ContextGraph:
    def __init__(self, client, scope='aftertrace', max_nodes=128):
        if not isinstance(scope, str) or not 1 <= len(scope) <= 80:
            raise ValueError('Scope must contain 1..80 characters')
        if type(max_nodes) is not int or not 1 <= max_nodes <= 256:
            raise ValueError('Node budget must be 1..256')
        self.client, self.max_nodes = client, max_nodes
        self.owner = scope + ':' + VERSION
        self.manifest_id = identity(self.owner + ':catalog')

    def _id(self, key):
        return identity(self.owner + ':' + key)

    def _manifest(self):
        return self.client.query('MATCH (n {id: $id}) RETURN n.key AS key, n.status AS status, n.fingerprint AS fingerprint', {'id': self.manifest_id})

    def _ready(self):
        rows = self._manifest()
        if not rows or rows[0]['key'] != self.owner + ':catalog' or rows[0]['status'] != 'ready':
            raise GraphError('Context catalog is not ready; run ingestion')

    def seed(self, db=None):
        own_db = db is None
        if own_db:
            db = warehouse('healthy')
        try:
            nodes, edges = catalog(db)
        finally:
            if own_db:
                db.close()
        if len(nodes) > self.max_nodes:
            raise GraphError('Catalog exceeds configured node budget')
        fingerprint = hashlib.sha256(json.dumps([nodes, edges], sort_keys=True).encode()).hexdigest()
        prior = self._manifest()
        if prior and (prior[0]['key'] != self.owner + ':catalog' or prior[0]['fingerprint'] != fingerprint):
            raise GraphError('Catalog identity/schema changed; use a new fixture version or scope')
        records = [dict(n, id=self._id(n['key']), owner=self.owner, key=self.owner + ':' + n['key']) for n in nodes]
        all_ids = [n['id'] for n in records] + [self.manifest_id]
        if len(set(all_ids)) != len(all_ids):
            raise GraphError('Catalog ID collision')
        for row in records:
            found = self.client.query('MATCH (n {id: $id}) RETURN n.key AS key', {'id': row['id']})
            if found and found[0]['key'] != row['key']:
                raise GraphError('Persistent ID collision; no metadata overwritten')
        self.client.query('UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Catalog, n.key = row.key, n.status = row.status, n.fingerprint = row.fingerprint', {'rows': [{'id': self.manifest_id, 'key': self.owner + ':catalog', 'status': 'pending', 'fingerprint': fingerprint}]})
        for kind in LABELS:
            selected = [r for r in records if r['kind'] == kind]
            if selected:
                self.client.query(f'UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{kind}, n.key = row.key, n.owner = row.owner, n.name = row.name, n.layer = row.layer, n.detail = row.detail', {'rows': selected})
        for rel in EDGE_LABELS:
            selected = [{'src': self._id(a), 'dst': self._id(b)} for a, r, b in edges if r == rel]
            if selected:
                self.client.query(f'UNWIND $rows AS row CREATE (a {{id: row.src}})-[:{rel}]->(b {{id: row.dst}})', {'rows': selected})
        # Partial ingestion never becomes queryable. Re-running the same input resumes it.
        self.client.query('MATCH (n {id: $id}) SET n.status = $status', {'id': self.manifest_id, 'status': 'ready'})
        result = self.context()
        if len(result['nodes']) != len(nodes) or len(result['edges']) != len(edges):
            self.client.query('MATCH (n {id: $id}) SET n.status = $status', {'id': self.manifest_id, 'status': 'pending'})
            raise GraphError('Ingestion reconciliation failed')
        return result

    def context(self):
        self._ready()
        nodes, edges = [], []
        for kind in LABELS:
            result = self.client.query(f'MATCH (n:{kind}) WHERE n.owner = $owner RETURN n.id AS id, n.name AS name, n.layer AS layer, n.detail AS detail ORDER BY id LIMIT $limit', {'owner': self.owner, 'limit': self.max_nodes + 1})
            nodes.extend(dict(r, kind=kind) for r in result)
        if len(nodes) > self.max_nodes:
            raise GraphError('Context node budget exceeded')
        ids = {n['id'] for n in nodes}
        for rel, kind in EDGE_LABELS.items():
            result = self.client.query(f'MATCH (a:{kind})-[:{rel}]->(b) WHERE a.owner = $owner RETURN a.id AS source, b.id AS target ORDER BY source, target LIMIT $limit', {'owner': self.owner, 'limit': self.max_nodes * 8 + 1})
            if len(result) > self.max_nodes * 8 or any(r['target'] not in ids for r in result):
                raise GraphError('Context edge budget or scope violation')
            edges.extend(dict(r, kind=rel) for r in result)
        return {'nodes': nodes, 'edges': edges, 'source': 'hydradb', 'owner': self.owner,
                'retrieved_nodes': len(nodes), 'retrieved_edges': len(edges)}

    def search(self, text, limit=10):
        if not isinstance(text, str) or not text.strip() or type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError('Non-empty search text and limit 1..32 required')
        return [n for n in self.context()['nodes'] if n['kind'] == 'Dataset' and text.casefold() in n['name'].casefold()][:limit]

    def upstream(self, field='delivery_fee_kpi.fee_cents', max_hops=3, limit=32):
        if type(max_hops) is not int or not 1 <= max_hops <= 4 or type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError('Traversal requires 1..4 hops and a 1..64 result budget')
        graph = self.context()
        target = next((n for n in graph['nodes'] if n['kind'] == 'Field' and n['name'] == field), None)
        if not target:
            raise GraphError('Unknown field in this catalog')
        # Query each bounded depth to retain the shortest distance; cycles never include self.
        result, seen = [], {target['id']}
        for depth in range(1, max_hops + 1):
            rows = self.client.query(f'MATCH (a:Field)-[:DERIVES*{depth}..{depth}]->(b {{id: $target}}) WHERE a.owner = $owner RETURN DISTINCT a.id AS id, a.name AS name ORDER BY id LIMIT $limit', {'target': target['id'], 'owner': self.owner, 'limit': limit + 1})
            for row in rows:
                if row['id'] not in seen:
                    seen.add(row['id'])
                    result.append(dict(row, depth=depth, source='hydradb'))
            if len(result) > limit or len(rows) > limit:
                raise GraphError('Traversal budget exceeded; request a narrower neighborhood')
        return result

    def field_context(self, field, max_hops=3):
        graph = self.context()
        target = next((n for n in graph['nodes'] if n['kind'] == 'Field' and n['name'] == field), None)
        if target is None:
            raise GraphError('Unknown field in this catalog')
        upstream = self.upstream(field, max_hops)
        ids = {target['id']} | {n['id'] for n in upstream}
        contracts, tools = {}, {}
        for fid in sorted(ids):
            for row in self.client.query('MATCH (f {id: $id})-[:GOVERNED_BY]->(c) RETURN c.id AS id, c.name AS name, c.detail AS detail, c.layer AS version ORDER BY id', {'id': fid}):
                contracts[row['id']] = row
            for row in self.client.query('MATCH (t:Tool)-[:INSPECTS]->(f {id: $id}) WHERE t.owner = $owner RETURN t.id AS id, t.name AS name, t.detail AS detail ORDER BY id', {'id': fid, 'owner': self.owner}):
                tools[row['id']] = row
        return {'field': target, 'upstream': upstream, 'contracts': list(contracts.values()),
                'tools': list(tools.values()), 'source': 'hydradb', 'owner': self.owner,
                'retrieval': {'hops': max_hops, 'fields': len(ids), 'contracts': len(contracts), 'tools': len(tools)}}
