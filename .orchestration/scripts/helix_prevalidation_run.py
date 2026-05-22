#!/usr/bin/env python3
"""
Helix prevalidation runner wrapper.
This script runs the metadata extractor, builds the swe-runner command safely
(by flattening nested lists and converting all elements to strings), and then
invokes the swe-runner. It tolerates missing GITHUB_BASE_REF when run outside
of GitHub Actions by accepting explicit --base/--head flags.
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
    """Flatten nested lists/tuples and convert each element to string."""
    for item in seq:
        if isinstance(item, (list, tuple)):
            for inner in flatten_and_str(item):
                yield str(inner)
        else:
            yield str(item)


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

    # Example construction of swe-runner command. Real configs may supply a path/list.
    swe_runner_path = cfg.get('metadata', {}).get('swe_runner_path') or 'swe-runner'
    swe_args = cfg.get('metadata', {}).get('swe_runner_args') or []

    if args.image:
        # If an image was provided on CLI, prefer it
        swe_args = ["--image", args.image] + list(swe_args)

    swe_runner_cmd = [swe_runner_path,] + list(swe_args)

    # Defensive: ensure all elements are strings and flatten nested lists
    swe_runner_cmd_safe = list(flatten_and_str(swe_runner_cmd))

    # Build a shell-quoted command string for logging or system exec
    swe_runner_cmd_str = ' '.join(shlex.quote(s) for s in swe_runner_cmd_safe)

    print('\nSTAGE: Running swe-runner (command will be shown).')
    print('COMMAND: ' + swe_runner_cmd_str)

    if args.dry_run:
        print('Dry run: not executing swe-runner.')
        return

    # Execute the command in a subprocess (shell=False with list of args)
    try:
        # Use the safe flattened list when invoking directly
        ret = subprocess.call(swe_runner_cmd_safe, cwd=REPO_ROOT)
        if ret != 0:
            print(f'swe-runner exited with code {ret}', file=sys.stderr)
            sys.exit(ret)
    except FileNotFoundError:
        print('ERROR: swe-runner binary not found: ' + swe_runner_cmd_safe[0], file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        print('ERROR: failed to run swe-runner: ' + str(ex), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
