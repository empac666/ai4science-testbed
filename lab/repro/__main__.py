import argparse
import json
import sys
from .runner import run, export_case


def main():
    p = argparse.ArgumentParser(description='EV-1.0 run recorder')
    sub = p.add_subparsers(dest='action', required=True)
    r = sub.add_parser('run')
    r.add_argument('--name', required=True)
    r.add_argument('--inputs', nargs='+', default=[])
    r.add_argument('--metrics-from')
    r.add_argument('--parse', choices=['fw', 'pytest', 'json'])
    r.add_argument('cmd', nargs=argparse.REMAINDER)
    e = sub.add_parser('export-case')
    e.add_argument('case_dir')
    e.add_argument('--runs', nargs='+', required=True)
    e.add_argument('--claims', required=True)
    e.add_argument('--report', required=True)
    dclink = sub.add_parser('dclink-check')
    dclink.add_argument('--diagnose-missing-make', action='store_true', help='add a separately labeled direct-build diagnostic when make is absent')
    args = p.parse_args()
    try:
        if args.action == 'run':
            cmd = args.cmd[1:] if args.cmd[:1] == ['--'] else args.cmd
            rec = run(args.name, cmd, args.inputs, args.metrics_from, args.parse)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            return 1 if rec['exit_code'] or rec.get('parse_error') else 0
        if args.action == 'export-case':
            print(export_case(args.case_dir, args.runs, args.claims, args.report))
            return 0
        from .dclink import dclink_check
        return dclink_check(args.diagnose_missing_make)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
