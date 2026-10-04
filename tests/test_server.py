import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'queue'))
import serve_board


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local board ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        (self.root / 'queue').mkdir()
        (self.root / 'queue/board.html').write_text('demo workbench')
        (self.root / '.env').write_text('placeholder')
        (self.root / '.git').mkdir()
        (self.root / '.git/config').write_text('placeholder')
        skill = self.root / '.agents/skills/example'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('portable skill')
        outside = self.root.parent / 'outside.txt'
        outside.write_text('external')
        self.symlink_available = True
        try:
            (self.root / 'outside-link.txt').symlink_to(outside)
        except OSError as error:
            if sys.platform == 'win32' and error.winerror == 1314:
                self.symlink_available = False
            else:
                raise
        self.patch = patch.object(serve_board, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(serve_board.LocalHandler, directory=str(self.root)))
        self.server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.url = f'http://127.0.0.1:{server.server_port}'

    def test_home_and_skill_reading(self):
        with self.opener.open(self.url + '/', timeout=5) as response:
            self.assertEqual(response.read(), b'demo workbench')
        with self.opener.open(self.url + '/.agents/skills/example/SKILL.md', timeout=5) as response:
            self.assertEqual(response.read(), b'portable skill')

    def test_hidden_files_directory_listing_and_external_links_blocked(self):
        for relative in ('/.env', '/%2egit/config', '/queue/', '/%2eprivate/automation/state.json', '/queue/../.env', '/queue/%5c../.env'):
            with self.subTest(path=relative), self.assertRaises(urllib.error.HTTPError) as caught:
                self.opener.open(self.url + relative, timeout=5)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_external_symlink_blocked(self):
        if not self.symlink_available:
            self.skipTest('Windows account cannot create symlinks')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.opener.open(self.url + '/outside-link.txt', timeout=5)
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()
