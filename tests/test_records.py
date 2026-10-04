"""Regression coverage for migration, readiness gates and first installation."""
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'queue'))
import build_board
from project_records import load_project, render_markdown


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aigc workspace ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects' / 'demo-rooftop'
        shutil.copytree(ROOT / 'projects' / 'demo-rooftop', self.project)

    def modify(self, name, edit):
        path = self.project / name
        data = yaml.safe_load(path.read_text())
        edit(data)
        path.write_text(yaml.safe_dump(data, allow_unicode=True))

    def test_planned_shots_are_not_generated_or_passed(self):
        with patch.object(build_board, 'ROOT', self.root), patch.object(build_board, 'PROJECTS', self.root / 'projects'):
            project = build_board.collect_projects({}, {})[0]
        self.assertEqual((project['expected_shots'], project['generated'], project['passed']), (3, 0, 0))
        self.assertEqual(project['assets']['total'], 3)
        self.assertEqual(project['shot_prompts'][1]['reference_asset_ids'], ['C01', 'S01', 'P01'])

    def test_ready_rejects_draft_and_missing_reference(self):
        with self.assertRaisesRegex(ValueError, 'uploaded'):
            load_project(self.project, ready=True)
        self.modify('assets/asset-matrix.yaml', lambda d: [a.update(status='uploaded') for a in d['assets']])
        self.assertIsNotNone(load_project(self.project, ready=True))
        (self.project / 'assets/characters/C01-robot-turnaround-v01.svg').unlink()
        with self.assertRaisesRegex(ValueError, 'must exist'):
            load_project(self.project, ready=True)

    def test_camera_gate_does_not_accept_missing_stop(self):
        self.modify('assets/asset-matrix.yaml', lambda d: [a.update(status='uploaded') for a in d['assets']])
        self.modify('prompts/shots.yaml', lambda d: d['shots'][0]['camera'].update(stop=''))
        self.assertIsNotNone(load_project(self.project))
        with self.assertRaisesRegex(ValueError, 'camera'):
            load_project(self.project, ready=True)

    def test_bad_references_and_version_fail_loudly(self):
        self.modify('prompts/shots.yaml', lambda d: d['shots'][0].update(references=['C99']))
        with self.assertRaisesRegex(ValueError, 'unknown reference'):
            load_project(self.project)
        self.modify('prompts/shots.yaml', lambda d: d.update(version=2))
        with self.assertRaisesRegex(ValueError, 'version'):
            load_project(self.project)

    def test_duplicate_shots_and_path_escape_rejected(self):
        self.modify('prompts/shots.yaml', lambda d: d['shots'].append(copy.deepcopy(d['shots'][0])))
        with self.assertRaisesRegex(ValueError, 'unique'):
            load_project(self.project)
        self.modify('prompts/shots.yaml', lambda d: d['shots'].pop())
        self.modify('assets/asset-matrix.yaml', lambda d: d['assets'][0].update(image='../../outside.svg'))
        with self.assertRaisesRegex(ValueError, 'path must remain within'):
            load_project(self.project)

    def test_symlink_reference_cannot_read_outside_project(self):
        outside = self.root / 'private.svg'
        outside.write_text('<svg/>')
        link = self.project / 'assets/characters/external.svg'
        try:
            link.symlink_to(outside)
        except OSError as error:
            if sys.platform == 'win32' and error.winerror == 1314:
                self.skipTest('Windows account cannot create symlinks')
            raise
        self.modify('assets/asset-matrix.yaml', lambda d: d['assets'][0].update(image='characters/external.svg'))
        with self.assertRaisesRegex(ValueError, 'path must remain within'):
            load_project(self.project)

    def test_old_markdown_summary_uses_actual_inventory(self):
        folder = self.root / 'legacy'
        (folder / 'assets/characters').mkdir(parents=True)
        (folder / 'assets/characters/C01.png').write_bytes(b'example')
        (folder / 'assets/asset-matrix.md').write_text('# 资产\n\n**状态**：不同措辞，无法通过旧摘要句解析。\n\n## 人物\n\n| C01 | robot | 01 | `characters/C01.png` | `prompts/assets/C01.md` | 已上传 |\n')
        with patch.object(build_board, 'ROOT', self.root):
            self.assertEqual(build_board.asset_summary(folder)['total'], 1)
        (folder / 'assets/characters/C01.png').unlink()
        with patch.object(build_board, 'ROOT', self.root):
            self.assertEqual(build_board.asset_summary(folder)['total'], 0)

    def test_render_is_repeatable_and_keeps_camera(self):
        render_markdown(self.project)
        first = (self.project / 'prompts/shot-prompts.md').read_text()
        render_markdown(self.project)
        self.assertEqual(first, (self.project / 'prompts/shot-prompts.md').read_text())
        self.assertIn('**stop**', first)
        self.assertIn('### 03', first)

    def test_scaffold_in_foreign_directory_and_duplicate_guard(self):
        location = self.root / 'new clone with spaces'
        for relative in ('projects/new_project.py', 'queue/project_records.py', 'queue/storage.py'):
            dest = location / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dest)
        command = [sys.executable, str(location / 'projects/new_project.py'), 'new-story', '--title', '新的作品']
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        project = location / 'projects/new-story'
        for relative in ('assets/asset-matrix.md', 'prompts/shot-prompts.md', 'assets/audio/source.yaml', 'shot_audit.md', 'run-log.md'):
            self.assertTrue((project / relative).is_file(), relative)
        self.assertEqual(load_project(project)['shots'], [])
        (project / 'script.md').write_text('user edit')
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual((project / 'script.md').read_text(), 'user edit')

    def test_install_skill_without_workspace_or_overwrite(self):
        target = self.root / 'agent skills'
        command = [sys.executable, str(ROOT / 'scripts/install_skill.py'), '--skills-dir', str(target)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        skill = target / 'runninghub-minimax-story-video'
        self.assertTrue((skill / 'references/records.md').is_file())
        self.assertFalse((skill / 'queue').exists())
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_malformed_yaml_and_incomplete_contract_do_not_overwrite_views(self):
        before = (self.project / 'storyboard.md').read_bytes()
        (self.project / 'prompts/shots.yaml').write_text('shots: [invalid', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'malformed YAML'):
            render_markdown(self.project)
        self.assertEqual((self.project / 'storyboard.md').read_bytes(), before)
        (self.project / 'prompts/shots.yaml').unlink()
        with self.assertRaisesRegex(ValueError, 'all three'):
            load_project(self.project)

    def test_nan_duration_duplicate_coverage_and_audit_mismatch_rejected(self):
        self.modify('prompts/shots.yaml', lambda d: d['shots'][0].update(duration_seconds=float('nan')))
        with self.assertRaisesRegex(ValueError, 'finite'):
            load_project(self.project)
        self.modify('prompts/shots.yaml', lambda d: d['shots'][0].update(duration_seconds=5))
        self.modify('assets/asset-matrix.yaml', lambda d: d['assets'][0].update(shots=[1, 1]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            load_project(self.project)
        self.modify('assets/asset-matrix.yaml', lambda d: d['assets'][0].update(shots=[1, 2, 3]))
        self.modify('shot_audit.yaml', lambda d: d['records'][0].update(duration_seconds=99))
        with self.assertRaisesRegex(ValueError, 'audit duration'):
            load_project(self.project)

    def test_registered_video_is_project_relative_and_playable_link_is_kept(self):
        path = self.project / 'generated/shots/01 my video.mp4'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'video fixture')
        self.modify('shot_audit.yaml', lambda d: d['records'][0].update(state='generated', video='generated/shots/01 my video.mp4'))
        with patch.object(build_board, 'ROOT', self.root), patch.object(build_board, 'PROJECTS', self.root / 'projects'):
            project = build_board.collect_projects({}, {})[0]
        self.assertEqual(project['shots'][0]['file'], 'projects/demo-rooftop/generated/shots/01 my video.mp4')
        path.unlink()
        with patch.object(build_board, 'ROOT', self.root), patch.object(build_board, 'PROJECTS', self.root / 'projects'):
            self.assertEqual(build_board.collect_projects({}, {})[0]['shots'][0]['file'], '')

    def test_queued_external_project_rejected(self):
        queue = {'items': [{'project': 'projects/../../outside', 'task': 'render'}]}
        with patch.object(build_board, 'ROOT', self.root), patch.object(build_board, 'PROJECTS', self.root / 'projects'):
            with self.assertRaises(ValueError):
                build_board.collect_projects(queue, {})

    def test_windows_reserved_project_names_rejected(self):
        result = subprocess.run([sys.executable, str(ROOT / 'projects/new_project.py'), 'con', '--title', 'example'], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('slug', result.stderr)

    def test_builder_versions_bundle_urls_so_updates_bypass_stale_browser_cache(self):
        queue = self.root / 'queue'
        (queue / 'board-ui').mkdir(parents=True)
        shutil.copy2(ROOT / 'queue/board-ui/template.html', queue / 'board-ui/template.html')
        (queue / 'board.bundle.js').write_bytes(b'first bundle')
        (queue / 'board.bundle.css').write_bytes(b'styles')
        with patch.object(build_board, 'ROOT', self.root), patch.object(build_board, 'QUEUE', queue), patch.object(build_board, 'PROJECTS', self.root / 'projects'):
            build_board.main()
            first = (queue / 'board.html').read_text(encoding='utf-8')
            (queue / 'board.bundle.js').write_bytes(b'updated bundle')
            build_board.main()
        second = (queue / 'board.html').read_text(encoding='utf-8')
        match = r'board.bundle.js\?v=([a-f0-9]{16})'
        self.assertNotEqual(re.search(match, first).group(1), re.search(match, second).group(1))
        self.assertIn('board.bundle.css?v=', second)


if __name__ == '__main__':
    unittest.main()
