"""Run the synthetic fixture and emit real measurements and invariant results."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.fixture import BROKEN, FIXED, VERSION, measure, verify, warehouse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['healthy', 'duplicate', 'duplicate_heldout', 'stale'], default='duplicate')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--candidate', choices=['original', 'deduplicated'], default='original')
    args = parser.parse_args()
    db = warehouse(args.scenario, args.seed, FIXED if args.candidate == 'deduplicated' else BROKEN)
    try:
        checks = verify(db, args.seed)
        print(json.dumps({'fixture_version': VERSION, 'scenario': args.scenario, 'seed': args.seed,
                          'candidate': args.candidate, 'metrics': measure(db), 'checks': checks,
                          'all_passed': all(c['passed'] for c in checks)}, sort_keys=True))
    finally:
        db.close()


if __name__ == '__main__':
    main()
