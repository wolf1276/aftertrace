"""Introspect the healthy synthetic fixture and ingest its HydraDB context catalog."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import connect
from app.graph import ContextGraph
from hydra import HydraError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', default='aftertrace')
    parser.add_argument('--field', default='delivery_fee_kpi.fee_cents')
    args = parser.parse_args()
    try:
        graph = ContextGraph(connect(), args.scope)
        result = graph.seed()
        context = graph.field_context(args.field)
        print(json.dumps({'ok': True, 'source': result['source'], 'owner': result['owner'],
                          'nodes': result['retrieved_nodes'], 'edges': result['retrieved_edges'],
                          'context': context}, sort_keys=True))
        return 0
    except (HydraError, RuntimeError, ValueError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
