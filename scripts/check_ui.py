#!/usr/bin/env python3
"""Run optional real-browser regression checks through the installed Ego Lite CLI."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8767/queue/board.html')
    parser.add_argument('--space', type=int, help='resume this active agent-owned task space instead of creating one')
    parser.add_argument('--page', default='p1', help='bound page label when --space is supplied')
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('UI tests are restricted to the local workbench')
    if not shutil.which('ego-browser'):
        parser.error('install and open Ego Lite: https://lite.ego.app/')
    request = {'url': args.url, 'space': args.space, 'page': args.page}
    script = Path(__file__).with_suffix('.mjs').read_text(encoding='utf-8')
    result = subprocess.run(['ego-browser', 'nodejs'], input='const AIGC_UI_REQUEST = ' + json.dumps(request) + ';\n' + script, text=True, encoding='utf-8')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
