import argparse
import json
import sys
from pathlib import Path
from .checker import check_case, batch, evaluate


def main():
    parser = argparse.ArgumentParser(description='EV-1.0 deterministic evidence checker')
    sub = parser.add_subparsers(dest='action', required=True)
    check = sub.add_parser('check')
    check.add_argument('case_dir')
    check.add_argument('--json', action='store_true')
    b = sub.add_parser('batch')
    b.add_argument('directory')
    b.add_argument('--out', required=True)
    ev = sub.add_parser('evaluate')
    ev.add_argument('directory')
    ev.add_argument('--labels', required=True)
    ev.add_argument('--out')
    args = parser.parse_args()
    try:
        if args.action == 'check':
            result = check_case(args.case_dir)
            status = int(result['verdict'] == 'fail')
        elif args.action == 'batch':
            result = batch(args.directory)
            status = int(any(r['verdict'] == 'fail' for r in result.values()))
        else:
            result = evaluate(args.directory, json.loads(Path(args.labels).read_text(encoding='utf-8')))
            status = 0
        output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if getattr(args, 'out', None):
            Path(args.out).write_text(output + '\n', encoding='utf-8')
        if args.action != 'check' or args.json:
            print(output)
        else:
            print(result['verdict'])
            for item in result['errors'] + result['warnings']:
                print('{code} {where}: {detail}'.format(**item))
        return status
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
