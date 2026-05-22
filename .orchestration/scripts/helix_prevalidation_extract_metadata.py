#!/usr/bin/env python3
"""
Lightweight metadata extractor for Helix prevalidation.
Accepts --base and --head to run outside of GitHub Actions PR context.
Writes a JSON config to the requested --output path.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))


def run_git(cmd):
    try:
        out = subprocess.check_output(['git'] + cmd, cwd=REPO_ROOT, stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--base', help='Git ref for base (falls back to env GITHUB_BASE_REF)')
    p.add_argument('--head', help='Git ref for head (falls back to env GITHUB_HEAD_REF or GITHUB_REF)')
    args = p.parse_args()

    # Read metadata.json
    metadata_path = os.path.join(REPO_ROOT, '.helix', 'metadata.json')
    if not os.path.exists(metadata_path):
        print(f'ERROR: .helix/metadata.json not found at {metadata_path}', file=sys.stderr)
        sys.exit(1)

    with open(metadata_path, 'r', encoding='utf-8') as f:
        try:
            metadata = json.load(f)
        except Exception as ex:
            print('ERROR: failed to parse metadata.json: ' + str(ex), file=sys.stderr)
            sys.exit(1)

    # metadata.json can be an object or an array of objects; normalize to a dict
    if isinstance(metadata, list) and len(metadata) > 0:
        metadata = metadata[0]

    # Determine base/head refs
    base = args.base or os.environ.get('GITHUB_BASE_REF')
    head = args.head or os.environ.get('GITHUB_HEAD_REF') or os.environ.get('GITHUB_REF')

    if not base or not head:
        # Best-effort: try to infer from git
        current = run_git(['rev-parse', '--abbrev-ref', 'HEAD'])
        if current:
            head = head or current
        # try origin/main as base
        base = base or 'origin/main'

    # Collect recent commits (head)
    commits = []
    try:
        log = subprocess.check_output(['git', 'log', '--pretty=format:%h %s', '--max-count=20', head], cwd=REPO_ROOT)
        commits = log.decode().splitlines()
    except Exception:
        commits = []

    out = {
        'repo_root': REPO_ROOT,
        'metadata': metadata,
        'base': base,
        'head': head,
        'commits_head': commits,
    }

    # Print summary to stdout for visibility
    print('INFO: Repository root: ' + REPO_ROOT)
    if not os.environ.get('GITHUB_BASE_REF'):
        print('WARNING: GITHUB_BASE_REF not set - running in non-PR context (using provided or inferred refs)')
    print('STAGE: Extracting metadata from .helix/metadata.json')
    for k in ('problem_statement','problem_statement_variant','hints'):
        v = metadata.get(k)
        if v:
            print(f'INFO:   {k}: {str(v)[:120]}')

    print('\nSTAGE: Extracting commit information from git')
    if commits:
        print('INFO: Latest commits on head:')
        for c in commits:
            print('  ' + c)
    else:
        print('INFO: No commits found for head ref: ' + str(head))

    # Write to output path
    try:
        with open(args.output, 'w', encoding='utf-8') as out_f:
            json.dump(out, out_f, indent=2)
        print('WROTE: ' + args.output)
    except Exception as ex:
        print('ERROR: failed to write output: ' + str(ex), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
