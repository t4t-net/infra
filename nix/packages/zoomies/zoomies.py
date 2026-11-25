#!/usr/bin/env python3
"""zoomies: a tiny ci 4 th fleet. `zoomies run --config <path>` does 1 tick, `zoomies status` is th tui"""
import argparse
import sys
import time


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "status":
        # lazy so th run side (nd its tests) never needs th tui module
        import status
        return status.main(argv[1:])

    ap = argparse.ArgumentParser(prog="zoomies")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="poll th branch nd build it if it moved (1 tick)")
    r.add_argument("--config", required=True)
    sub.add_parser("status", help="fleet tui (see `zoomies status --help`)")
    args = ap.parse_args(argv)

    import run
    cfg = run.load_config(args.config)
    return run.tick(cfg, run=run.real_run, now=lambda: int(time.time()), post=run.real_post)


if __name__ == "__main__":
    sys.exit(main())
