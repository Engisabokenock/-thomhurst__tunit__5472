#!/usr/bin/env python3
"""
Robust helix prevalidation runner used in CI.
Ensures swe-runner command elements are flattened and stringified to avoid TypeError when nested lists are present.
This file is intended to be committed directly to the golden-solution branch.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))


def flatten_and_str(seq):
    """Flatten nested sequences and convert elements to strings. For dicts, use JSON repr."""
    if seq is None:
        return []
    out = []
    # If a single string was passed, treat as single-element sequence
    if isinstance(seq, (str, bytes)):
        return [str(seq)]
    try:
        iterator = iter(seq)
    except TypeError:
        return [json.dumps(seq)]
    for item in iterator:
        if isinstance(item, (list, tuple)):
            out.extend(flatten_and_str(item))
        elif isinstance(item, dict):
            out.append(json.dumps(item, separators=(',', ':')))
        else:
            out.append(str(item))
    return out


def run_extractor(output_path, base=None, head=None):
    extractor = os.path.join(HERE, 'helix_prevalidation_extract_metadata.py')
    cmd = [sys.executable, extractor, '--output', output_path]
    if base:
        cmd += ['--base', base]
    if head:
        cmd += ['--head', head]
    print('Running extractor: ' + ' '.join(map(shlex.quote, cmd)))
    subprocess.check_call(cmd, cwd=REPO_ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image', help='Container image for swe-runner', default=None)
    p.add_argument('--config', help='Path to write/read metadata config', default=os.path.join(REPO_ROOT, 'helix_config.json'))
    p.add_argument('--base', help='Base ref (optional)')
    p.add_argument('--head', help='Head ref (optional)')
    p.add_argument('--dry-run', action='store_true', help='Do not actually exec swe-runner')
    args = p.parse_args()

    try:
        run_extractor(args.config, base=args.base, head=args.head)
    except subprocess.CalledProcessError as ex:
        print('ERROR: extractor failed: ' + str(ex), file=sys.stderr)
        sys.exit(1)

    # Load config
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception as ex:
        print('ERROR: failed to read config: ' + str(ex), file=sys.stderr)
        sys.exit(1)

    # metadata may contain swe-runner configuration; default to just 'swe-runner'
    meta = cfg.get('metadata', {}) if isinstance(cfg, dict) else {}
    swe_runner_path = meta.get('swe_runner_path') or 'swe-runner'
    swe_args = meta.get('swe_runner_args') or []

    # If CLI provided an image, prepend it to args; ensure we handle nested lists safely
    if args.image:
        swe_args = ["--image", args.image] + (swe_args if isinstance(swe_args, list) else [swe_args])

    # Build final command list by flattening and stringifying everything
    raw_cmd = [swe_runner_path]
    if isinstance(swe_args, (list, tuple)):
        raw_cmd.extend(swe_args)
    else:
        raw_cmd.append(swe_args)

    safe_cmd = flatten_and_str(raw_cmd)

    # Defensive logging
    try:
        cmd_str = ' '.join(shlex.quote(s) for s in safe_cmd)
    except Exception:
        # Fallback: JSON-encode elements then join
        cmd_str = ' '.join(json.dumps(s) for s in safe_cmd)

    print('\nSTAGE: Running swe-runner (command will be shown).')
    print('COMMAND: ' + cmd_str)

    if args.dry_run:
        print('Dry run: not executing swe-runner.')
        return

    # Execute the command
    try:
        ret = subprocess.call(safe_cmd, cwd=REPO_ROOT)
        if ret != 0:
            print(f'swe-runner exited with code {ret}', file=sys.stderr)
            sys.exit(ret)
    except FileNotFoundError:
        print('ERROR: swe-runner binary not found: ' + (safe_cmd[0] if safe_cmd else 'UNKNOWN'), file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        print('ERROR: failed to run swe-runner: ' + str(ex), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
