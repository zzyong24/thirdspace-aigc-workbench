#!/usr/bin/env python3
"""Validate project YAML, optionally apply submission gates, and render Markdown."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'queue'))
from project_records import load_project, render_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--check', action='store_true', help='validate without overwriting reading views')
    parser.add_argument('--ready', action='store_true', help='also check prompt, camera and uploaded reference gates')
    args = parser.parse_args()
    folder = args.project.resolve()
    try:
        if load_project(folder, ready=args.ready) is None:
            parser.error('project has no versioned YAML records')
        if not args.check:
            render_markdown(folder)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'Validated {folder.name}' + ('' if args.check else '; reading views refreshed'))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    main()
