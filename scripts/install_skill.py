#!/usr/bin/env python3
"""Install only the portable RunningHub Skill; never overwrite an existing install."""
import argparse
import shutil
from pathlib import Path

NAME = 'runninghub-minimax-story-video'
SOURCE = Path(__file__).resolve().parents[1] / '.agents' / 'skills' / NAME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills-dir', type=Path, default=Path.home() / '.codex' / 'skills')
    args = parser.parse_args()
    destination = args.skills_dir.expanduser() / NAME
    if destination.exists():
        parser.error('destination exists; review it before updating, or select a different --skills-dir')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    print(f'Installed {NAME}; restart or reload your agent to discover it.')


if __name__ == '__main__':
    main()
