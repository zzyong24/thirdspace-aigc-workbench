"""Versioned project records. YAML owns data; Markdown is a generated reading view."""
from __future__ import annotations
import math
import re
from pathlib import Path
import yaml

CATEGORIES = {'character': '人物', 'scene': '场景', 'prop': '道具'}
STATES = {'planned', 'running', 'generated', 'review', 'passed', 'redo'}
CAMERA_FIELDS = ('start', 'move', 'stop', 'continuity')


def record_file(folder: Path, relative: str, key: str) -> list[dict]:
    path = folder / relative
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError(f'{path}: expected version: 1')
    items = data.get(key)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f'{path}: {key} must be a list of records')
    return items


def local_path(folder: Path, relative: str) -> Path | None:
    if relative == "":
        return None
    if not isinstance(relative, str):
        raise ValueError('asset/video path must be text')
    if Path(relative).is_absolute() or not (folder / relative).resolve().is_relative_to(folder.resolve()):
        raise ValueError(f'path must remain within project: {relative}')
    return folder / relative


def duration(value: object) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise ValueError('duration_seconds must be a finite positive number')
    return value


def numbered(items: list[dict], kind: str) -> None:
    ids = [item.get('id') for item in items]
    if any(type(number) is not int or number < 1 for number in ids) or len(set(ids)) != len(ids):
        raise ValueError(f'{kind}: shot IDs must be unique positive integers')


def load_project(folder: Path, ready: bool = False) -> dict | None:
    names = ('assets/asset-matrix.yaml', 'prompts/shots.yaml', 'shot_audit.yaml')
    if not any((folder / name).exists() for name in names):
        if ready:
            raise ValueError('ready validation requires structured YAML records')
        return None
    assets = record_file(folder, names[0], 'assets')
    shots = record_file(folder, names[1], 'shots')
    audit = record_file(folder, names[2], 'records')
    numbered(shots, 'prompts')
    numbered(audit, 'audit')
    shot_ids = {shot['id'] for shot in shots}
    asset_ids = set()
    for asset in assets:
        asset_id = asset.get('id')
        if not isinstance(asset_id, str) or not re.fullmatch(r'[CSP]\d{2,}', asset_id) or asset_id in asset_ids:
            raise ValueError('asset IDs must be unique C/S/P IDs')
        asset_ids.add(asset_id)
        if asset.get('category') not in CATEGORIES or not isinstance(asset.get('name'), str):
            raise ValueError(f'{asset_id}: category and name are required')
        expected_prefix = {'character': 'C', 'scene': 'S', 'prop': 'P'}[asset['category']]
        if not asset_id.startswith(expected_prefix):
            raise ValueError(f'{asset_id}: ID does not match category')
        if asset.get('status') not in {'draft', 'generated', 'uploaded'}:
            raise ValueError(f'{asset_id}: invalid asset status')
        numbers = asset.get('shots', [])
        if not isinstance(numbers, list) or any(type(n) is not int or n not in shot_ids for n in numbers):
            raise ValueError(f'{asset_id}: unknown shot in coverage')
        local_path(folder / 'assets', asset.get('image', ''))
        local_path(folder, asset.get('prompt_file', ''))
        if type(asset.get('historical', False)) is not bool:
            raise ValueError(f'{asset_id}: historical must be boolean')
    if ready:
        for asset in assets:
            if asset.get('historical'):
                continue
            image = local_path(folder / 'assets', asset.get('image', ''))
            if asset['status'] != 'uploaded' or not image or not image.is_file():
                raise ValueError(f'{asset["id"]}: current reference must exist and be recorded as uploaded')
    for shot in shots:
        duration(shot.get('duration_seconds'))
        if not isinstance(shot.get('title'), str) or not isinstance(shot.get('prompt'), str):
            raise ValueError(f'shot {shot["id"]}: title and prompt are required')
        references = shot.get('references', [])
        if not isinstance(references, list) or any(not isinstance(ref, str) or ref not in asset_ids for ref in references):
            raise ValueError(f'shot {shot["id"]}: unknown reference asset')
        if len(set(references)) != len(references):
            raise ValueError(f'shot {shot["id"]}: duplicate references')
        camera = shot.get('camera', {})
        if not isinstance(camera, dict) or any(not isinstance(camera.get(key, ''), str) for key in CAMERA_FIELDS):
            raise ValueError(f'shot {shot["id"]}: invalid camera plan')
        if not isinstance(shot.get('settings', {}), dict):
            raise ValueError(f'shot {shot["id"]}: settings must be a mapping')
        if ready and (not shot['prompt'].strip() or any(not camera.get(key, '').strip() for key in CAMERA_FIELDS)):
            raise ValueError(f'shot {shot["id"]}: full camera plan and prompt are required before submission')
        if ready:
            planned = {a['id'] for a in assets if shot['id'] in a.get('shots', []) and not a.get('historical')}
            if set(references) != planned:
                raise ValueError(f'shot {shot["id"]}: references must match asset coverage')
            settings = shot.get('settings', {})
            if any(not isinstance(settings.get(key), str) or not settings[key].strip() for key in ('model', 'mode', 'aspect_ratio', 'resolution')):
                raise ValueError(f'shot {shot["id"]}: model, mode, aspect_ratio and resolution are required')
            for ref in references:
                asset = next(a for a in assets if a['id'] == ref)
                image = local_path(folder / 'assets', asset.get('image', ''))
                if asset.get('historical') or asset['status'] != 'uploaded' or not image or not image.is_file():
                    raise ValueError(f'{ref}: current reference must exist and be recorded as uploaded')
    for entry in audit:
        if entry['id'] not in shot_ids or entry.get('state') not in STATES:
            raise ValueError('audit must refer to a known shot and valid state')
        duration(entry.get('duration_seconds'))
        local_path(folder, entry.get('video', ''))
        if not isinstance(entry.get('notes', ''), str):
            raise ValueError('audit notes must be text')
    if ready and not shots:
        raise ValueError('at least one planned shot is required')
    return {'assets': assets, 'shots': shots, 'audit': audit}


def board_records(folder: Path, root: Path, records: dict) -> tuple[list, dict, list, list]:
    def existing(base: Path, relative: str) -> str:
        path = local_path(base, relative)
        return path.relative_to(root).as_posix() if path and path.is_file() else ''
    assets = [{
        'id': a['id'], 'name': a['name'], 'category': CATEGORIES[a['category']],
        'shots': '、'.join(f'{n:02}' for n in a.get('shots', [])) or '—',
        'status': {'draft': '示例 / 草稿；未上传', 'generated': '已生成；待上传', 'uploaded': '已登记上传；提交前核验'}[a['status']],
        'historical': a.get('historical', False), 'uploaded': a['status'] == 'uploaded',
        'image_name': a.get('image', ''), 'image': existing(folder / 'assets', a.get('image', '')),
        'prompt_file': existing(folder, a.get('prompt_file', '')),
    } for a in records['assets']]
    by_id = {a['id']: a for a in assets}
    coverage = {s['id']: [a['id'] for a in records['assets'] if s['id'] in a.get('shots', []) and not a.get('historical')] for s in records['shots']}
    prompts = []
    for shot in records['shots']:
        references = shot.get('references', [])
        camera = shot.get('camera', {})
        direction = '\n'.join(f'{key}: {camera.get(key, "")}' for key in CAMERA_FIELDS)
        prompts.append({'number': shot['id'], 'title': shot['title'], 'text': shot['prompt'] + '\n\n摄影调度\n' + direction,
            'references': [Path(by_id[ref]['image_name']).name or ref for ref in references],
            'reference_details': [{'name': Path(by_id[ref]['image_name']).name or ref, 'asset_id': ref, 'image': by_id[ref]['image']} for ref in references],
            'reference_asset_ids': references, 'planned_asset_ids': coverage[shot['id']]})
    labels = {'planned': '未提交', 'running': '运行中', 'generated': '已生成；待审片', 'review': '待审片', 'passed': '通过', 'redo': '需重做'}
    audit = [{'number': e['id'], 'duration': f'{e["duration_seconds"]} 秒', 'state': e['state'], 'verdict': labels[e['state']], 'notes': e.get('notes', '')} for e in records['audit']]
    return assets, coverage, prompts, audit


def render_markdown(folder: Path) -> None:
    records = load_project(folder)
    if records is None:
        raise ValueError('no structured records to render')
    def cell(value: object) -> str:
        return str(value).replace('|', '\\|').replace('\n', ' ')
    matrix = ['# 资产矩阵', '', '> 由 asset-matrix.yaml 生成；修改 YAML 后重新渲染。草稿图片不表示已上传或可提交。', '', '| ID | 类型 | 名称 | 镜头 | 三视图文件 | 状态 |', '|---|---|---|---|---|---|']
    for a in records['assets']:
        matrix.append('| ' + ' | '.join(cell(v) for v in (a['id'], CATEGORIES[a['category']], a['name'], a.get('shots', []), a.get('image', ''), a['status'])) + ' |')
    plan = ['# 逐镜提示词', '', '> 由 shots.yaml 生成；修改 YAML 后重新渲染。', '']
    storyboard = ['# 分镜脚本', '', '> 由 shots.yaml 生成；动作与完整摄影调度以 YAML 为准。', '']
    for s in records['shots']:
        lines = [f'### {s["id"]:02} · {s["title"]}', '', f'时长：{s["duration_seconds"]} 秒', '', '参考：' + '、'.join(s.get('references', [])), '', s['prompt'], '']
        lines += [f'- **{key}**：{s.get("camera", {}).get(key, "待设计")}' for key in CAMERA_FIELDS]
        plan += lines + ['', '参数：`' + str(s.get('settings', {})) + '`', '']
        storyboard += lines + ['']
    audit = ['# 审片记录', '', '> 由 shot_audit.yaml 生成。未提交镜头不能记为通过。', '', '| 镜号 | 时长 | 状态 | 备注 |', '|---|---|---|---|']
    for e in records['audit']:
        audit.append(f'| {e["id"]:02} | {e["duration_seconds"]} | {e["state"]} | {cell(e.get("notes", ""))} |')
    for relative, lines in [('assets/asset-matrix.md', matrix), ('prompts/shot-prompts.md', plan), ('storyboard.md', storyboard), ('shot_audit.md', audit)]:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
