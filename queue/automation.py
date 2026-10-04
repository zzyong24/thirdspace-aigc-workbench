#!/usr/bin/env python3
"""Execute versioned jobs with durable state, dependency gates and recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import yaml
from project_records import load_project, render_markdown
from storage import atomic_text, within

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {'render', 'check_ready', 'inspect_runninghub', 'generate_runninghub'}
TERMINAL = {'done', 'failed', 'waiting_browser', 'waiting_balance', 'uncertain'}


def read_mapping(path):
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as error:
        raise ValueError(f'{path.name}: malformed YAML') from error
    if not isinstance(data, dict):
        raise ValueError(f'{path.name}: expected a mapping')
    return data


def jobs_from(root, filename='queue/automation.yaml'):
    config = read_mapping(within(root, filename))
    jobs = config.get('jobs')
    if type(config.get('version')) is not int or config['version'] != 1 or not isinstance(jobs, list):
        raise ValueError('automation requires version: 1 and jobs: []')
    by_id = {}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get('id'), str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', str(job.get('id', ''))):
            raise ValueError('every job requires a lowercase-hyphenated id')
        if job['id'] in by_id or job.get('action') not in ACTIONS:
            raise ValueError('duplicate job ID or unsupported action')
        project = within(root / 'projects', str(job.get('project', '')).removeprefix('projects/'))
        if not project.is_dir() or not (project / 'project.yaml').is_file():
            raise ValueError(f'{job["id"]}: project must be an existing projects/<slug> folder')
        if project.parent.resolve() != (root / 'projects').resolve():
            raise ValueError('project must be a direct child of projects/')
        dependencies = job.get('depends_on', [])
        if not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies) or len(set(dependencies)) != len(dependencies):
            raise ValueError('depends_on must be a list of unique job IDs')
        if type(job.get('enabled', True)) is not bool:
            raise ValueError('enabled must be boolean')
        if job['action'] == 'generate_runninghub':
            shots = job.get('shots')
            if not isinstance(shots, list) or not shots or any(type(n) is not int or n < 1 for n in shots) or len(set(shots)) != len(shots):
                raise ValueError('generation requires a nonempty list of unique positive shot IDs')
        by_id[job['id']] = {**job, 'project': project.relative_to(root).as_posix()}
    visited, visiting = set(), set()
    def visit(job_id):
        if job_id not in by_id:
            raise ValueError(f'unknown dependency: {job_id}')
        if job_id in visiting:
            raise ValueError('dependency cycle')
        if job_id in visited:
            return
        visiting.add(job_id)
        for dependency in by_id[job_id].get('depends_on', []):
            visit(dependency)
        visiting.remove(job_id)
        visited.add(job_id)
        ordered.append(by_id[job_id])
    ordered = []
    for job_id in by_id:
        visit(job_id)
    return ordered


def signature(root, job):
    digest = hashlib.sha256(json.dumps(job, sort_keys=True).encode())
    folder = root / job['project']
    # Generated Markdown is intentionally excluded; renders must be idempotent.
    for relative in ('project.yaml', 'assets/asset-matrix.yaml', 'prompts/shots.yaml', 'shot_audit.yaml'):
        path = within(folder, relative)
        digest.update(relative.encode())
        digest.update(path.read_bytes() if path.exists() else b'')
    if job['action'] in {'check_ready', 'generate_runninghub'}:
        records = load_project(folder)
        for asset in (records or {}).get('assets', []):
            if asset.get('image'):
                path = within(folder / 'assets', asset['image'])
                digest.update(path.read_bytes() if path.is_file() else b'missing image')
    return digest.hexdigest()


class RunLock:
    """Atomic mkdir works on Windows/macOS/Linux; abandoned locks need recovery."""
    def __init__(self, folder):
        self.folder = folder
    def __enter__(self):
        self.folder.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.folder.mkdir()
        except FileExistsError as error:
            raise ValueError('runner lock exists; check status, then use recover-lock after the process has stopped') from error
        atomic_text(self.folder / 'owner.json', json.dumps({'pid': os.getpid(), 'host': socket.gethostname()}))
        return self
    def __exit__(self, *_):
        (self.folder / 'owner.json').unlink()
        self.folder.rmdir()


def read_state(root):
    path = root / '.private/automation/state.json'
    if not path.exists():
        return {'version': 1, 'jobs': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or not isinstance(data.get('jobs'), dict) or any(not isinstance(v, dict) for v in data['jobs'].values()):
        raise ValueError('invalid automation state; preserve it and inspect manually')
    return data


def save_state(root, state):
    atomic_text(root / '.private/automation/state.json', json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def plan(root, jobs, state):
    result = []
    completed = set()
    for job in jobs:
        previous = state['jobs'].get(job['id'], {})
        current = signature(root, job)
        if not job.get('enabled', True):
            status, reason = 'disabled', 'job disabled'
        elif previous.get('state') in {'running', 'uncertain', 'waiting_browser', 'waiting_balance', 'failed'}:
            status, reason = previous['state'], 'explicit recovery required; original browser/job identity is retained'
        elif previous.get('state') == 'done' and previous.get('signature') == current:
            status, reason = 'done', 'already complete with these inputs'
            completed.add(job['id'])
        elif previous.get('state') == 'done' and job['action'] in {'inspect_runninghub', 'generate_runninghub'}:
            status, reason = 'changed', 'browser job inputs changed; inspect and explicitly recover'
        elif any(d not in completed for d in job.get('depends_on', [])):
            status, reason = 'waiting_dependency', 'dependency is unfinished or its input changed'
        else:
            status, reason = 'ready', 'dependencies satisfied'
        result.append({'id': job['id'], 'action': job['action'], 'state': status, 'reason': reason})
    return result


def point_gate(root, job, budget, now=None):
    if type(budget) is not int or budget <= 0:
        raise ValueError('generate_runninghub requires --point-budget from the current user')
    index = read_mapping(root / 'queue/index.yaml')
    policy = index.get('execution_policy', {})
    ceiling = policy.get('point_budget_per_run', 0)
    if policy.get('allow_existing_runninghub_points_at_21_00') is not True or type(ceiling) is not int or ceiling <= 0:
        raise ValueError('points policy disabled or configured budget invalid')
    if policy.get('may_spend_rmb_wallet_or_purchase_topups') is not False:
        raise ValueError('cash and top-ups must remain forbidden')
    if budget > ceiling:
        raise ValueError('authorized budget exceeds configured point_budget_per_run')
    start = index.get('credit_queue_check_start', '21:00')
    end = index.get('credit_queue_check_end', '22:00')
    if not all(isinstance(s, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', s) for s in (start, end)) or start == end:
        raise ValueError('points window must be distinct HH:MM start and end')
    local = (now or datetime.now().astimezone()).astimezone(ZoneInfo(index.get('timezone', 'Asia/Shanghai')))
    current = local.strftime('%H:%M')
    inside = start <= current < end if start < end else current >= start or current < end
    if not inside:
        raise ValueError(f'outside points window {start}–{end} {index.get("timezone")}')
    records = load_project(root / job['project'], ready=True)
    if not set(job['shots']) <= {s['id'] for s in records['shots']}:
        raise ValueError('job refers to unknown shots')
    return local.isoformat(), local.date().isoformat()


def canvas_url(root, job):
    url = read_mapping(root / job['project'] / 'project.yaml').get('canvas_url')
    if job['action'] == 'inspect_runninghub' and not url:
        url = 'https://www.runninghub.cn/'
    parsed = urlsplit(url or '')
    if parsed.scheme != 'https' or parsed.hostname not in {'runninghub.cn', 'www.runninghub.cn', 'runninghub.ai', 'www.runninghub.ai', 'rhtv.runninghub.cn', 'rhtv.runninghub.ai'} or parsed.username or parsed.password:
        raise ValueError('project.yaml needs an HTTPS RunningHub canvas_url')
    if job['action'] == 'generate_runninghub' and (parsed.path in {'', '/'} or not url):
        raise ValueError('generation needs the exact existing canvas URL')
    return url


def browser_inspect(root, job, directory, timeout):
    command = shutil.which('ego-browser')
    if not command:
        raise ValueError('ego-browser missing; install/onboard Ego Lite: https://lite.ego.app/')
    url = canvas_url(root, job)
    request = {'project': Path(job['project']).name, 'url': url, 'stateFile': str(directory / 'browser.json')}
    script = root / '.agents/skills/runninghub-minimax-story-video/scripts/inspect_browser.mjs'
    result = subprocess.run([command, 'nodejs'], input='const AIGC_BROWSER_REQUEST = ' + json.dumps(request) + ';\n' + script.read_text(encoding='utf-8'), text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, cwd=root)
    atomic_text(directory / 'browser-output.log', result.stdout + '\n' + result.stderr)
    if result.returncode:
        raise ValueError('Ego inspection failed; inspect private browser-output.log, retain original browser binding')
    # Runtime may print additional lines; validate our unique final JSON envelope.
    report = None
    for line in (result.stdout + '\n' + result.stderr).splitlines():
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get('spaceId'), int) and candidate.get('url') and 'snapshot' in candidate:
            report = candidate
    if not report:
        raise ValueError('Ego returned no browser observation')
    atomic_text(directory / 'observation.json', json.dumps(report, ensure_ascii=False, indent=2))
    return {'observation': 'observation.json', 'spaceId': report['spaceId'], 'result': 'observed; login/model/cost still require live inspection'}


def generate(root, job, directory, budget, timeout, agent_model):
    command = shutil.which('codex')
    if not command or not shutil.which('ego-browser'):
        raise ValueError('Codex CLI and Ego Lite are required; run doctor --browser')
    url = canvas_url(root, job)
    # Reuse a project-wide binding across jobs (inspect and generate).
    binding_file = root / '.private/automation/projects' / Path(job['project']).name / 'browser.json'
    if not binding_file.is_file():
        raise ValueError('inspect_runninghub must establish the original browser binding first')
    binding = json.loads(binding_file.read_text(encoding='utf-8'))
    if not isinstance(binding, dict) or type(binding.get('spaceId')) is not int or binding['spaceId'] <= 0 or not isinstance(binding.get('page'), str) or not re.fullmatch(r'p[1-9]\d*', binding['page']):
        raise ValueError('invalid browser binding; inspect original space without creating a replacement')
    if binding.get('url') != url:
        raise ValueError('browser binding does not match canvas_url; recover before changing canvas')
    authorization_time, authorization_day = point_gate(root, job, budget)
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['job_id', 'status', 'spent_points', 'shots', 'reason'], 'properties': {
        'job_id': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['generated', 'waiting_browser', 'waiting_balance', 'uncertain']},
        'spent_points': {'type': 'number'}, 'reason': {'type': 'string'},
        'shots': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['id', 'node_id', 'playable', 'evidence'], 'properties': {'id': {'type': 'integer'}, 'node_id': {'type': 'string'}, 'playable': {'type': 'boolean'}, 'evidence': {'type': 'string'}}}}}}
    schema_path, output = directory / 'result-schema.json', directory / 'agent-result.json'
    atomic_text(schema_path, json.dumps(schema))
    output.unlink(missing_ok=True)
    prompt = f'''Execute this explicitly authorized RunningHub job in this workspace. Read AGENTS.md, {job['project']}/AGENTS.md and .agents/skills/runninghub-minimax-story-video/SKILL.md. Find and read the installed ego-browser Skill; if absent return waiting_browser without acting. Do NOT spawn subagents.
Job: {json.dumps(job, ensure_ascii=False)}
Browser binding: {json.dumps(binding)}. Resume this EXACT space with taskSpace({binding['spaceId']}); do not open another space, claim user-owned spaces, or bypass a handoff. Canvas: {url}.
Current user's authorization: at most {budget} EXISTING RunningHub points TOTAL for this one job, granted {authorization_time}, valid only {authorization_day} in the configured window. No cash, purchases, topups, or image-generation charges. Before EVERY submission check live clock/window, live per-node price/type/balance and cumulative spend. Stop when the window or budget is exhausted. Authorization never survives a new process/recovery. Check original tasks BEFORE submitting; no duplicate submissions. Inspect current exact model, references, duration, aspect and resolution against YAML. Do not write prompts into unrelated nodes.
Generate ONLY specified unfinished/rejected shots using current references. Do not claim aesthetic audit passed. Record node identity, actual price and result in project run-log and shot_audit.yaml (generated or review). Save screenshots of each original task and playable output to {directory}; return their relative filenames as evidence. Do not download videos unless user requested it. Never mark done from an editor draft. Login/CAPTCHA/control prompt: handOff original space, return waiting_browser. Timeout/ambiguous submission: return uncertain, retain task identity, never retry. Keep the result canvas visible at completion. Return schema JSON only; generated means EVERY requested output is visibly playable, with evidence. A process exit code is not success evidence.'''
    invoke_agent(root, prompt, schema_path, output, directory, timeout, 'workspace-write', agent_model)
    report = json.loads(output.read_text(encoding='utf-8'))
    validate_result(root, job, directory, report, budget)
    return report


def invoke_agent(root, prompt, schema_path, output, directory, timeout, sandbox='read-only', agent_model=None):
    command = shutil.which('codex')
    if not command:
        raise ValueError('Codex CLI missing')
    with (directory / 'agent-output.log').open('w', encoding='utf-8') as log:
        model_args = ['--model', agent_model] if agent_model else []
        process = subprocess.Popen([command, 'exec', '--ephemeral', '--color', 'never', '-s', sandbox, '-c', 'sandbox_workspace_write.network_access=true', '-C', str(root), '--output-schema', str(schema_path), '-o', str(output), *model_args, '-'], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, encoding='utf-8', start_new_session=os.name != 'nt')
        try:
            process.communicate(prompt, timeout=timeout)
        except BaseException:
            if os.name != 'nt':
                import signal
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    if process.returncode or not output.is_file():
        raise ValueError('agent failed or returned no structured result; original task status must be inspected')


def validate_result(root, job, directory, report, budget):
    if not isinstance(report, dict) or report.get('job_id') != job['id'] or report.get('status') not in {'generated', 'waiting_browser', 'waiting_balance', 'uncertain'}:
        raise ValueError('invalid/mismatched agent result')
    points = report.get('spent_points')
    if type(points) not in (float, int) or not math.isfinite(points) or points < 0 or points > budget:
        raise ValueError('invalid or over-budget spend report; inspect actual account')
    if report['status'] != 'generated':
        return
    shots = report.get('shots')
    if not isinstance(shots, list) or len(shots) != len(job['shots']) or any(not isinstance(s, dict) or type(s.get('id')) is not int for s in shots) or {s.get('id') for s in shots} != set(job['shots']):
        raise ValueError('missing/duplicate output shots')
    for shot in shots:
        evidence = within(directory, shot.get('evidence', ''))
        if not shot.get('node_id') or shot.get('playable') is not True or not evidence.is_file() or evidence.stat().st_size == 0 or evidence.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
            raise ValueError('playable node identity and screenshot evidence required for every shot')
    audit = load_project(root / job['project'])['audit']
    if any(not any(a['id'] == n and a['state'] in {'generated', 'review', 'passed'} for a in audit) for n in job['shots']):
        raise ValueError('generated outputs are not registered in project audit')


def execute(root, jobs, selected=None, budget=0, timeout=1800, agent_model=None):
    private = root / '.private/automation'
    outcomes = []
    with RunLock(private / 'runner.lock'):
        state = read_state(root)
        for job in jobs:
            if selected and selected != job['id']:
                continue
            row = next(r for r in plan(root, jobs, state) if r['id'] == job['id'])
            if row['state'] != 'ready':
                outcomes.append(row)
                continue
            if job['action'] == 'generate_runninghub':
                if selected != job['id']:
                    outcomes.append({**row, 'state': 'waiting_authorization', 'reason': 'select one job and pass --point-budget; paid jobs never run in bulk'})
                    continue
                if not agent_model:
                    raise ValueError('choose a CLI-supported --agent-model; desktop model aliases may not work in Codex CLI')
                point_gate(root, job, budget)  # Preflight errors do not consume the job.
            folder = root / job['project']
            directory = private / 'projects' / folder.name
            directory.mkdir(parents=True, exist_ok=True)
            entry = {'state': 'running', 'signature': signature(root, job), 'started_at': datetime.now().astimezone().isoformat(), 'action': job['action']}
            if job['action'] == 'generate_runninghub':
                directory = private / 'runs' / (job['id'] + '-' + uuid.uuid4().hex)
                directory.mkdir(parents=True)
                entry['run_directory'] = directory.relative_to(root).as_posix()
            state['jobs'][job['id']] = entry
            save_state(root, state)  # Write-ahead: killed processes cannot resubmit.
            try:
                if job['action'] == 'render':
                    render_markdown(folder)
                    result = {'result': 'YAML validated and Markdown rendered'}
                elif job['action'] == 'check_ready':
                    load_project(folder, ready=True)
                    result = {'result': 'local readiness gates passed; live upload/fees unverified'}
                elif job['action'] == 'inspect_runninghub':
                    result = browser_inspect(root, job, directory, min(timeout, 60))
                else:
                    result = generate(root, job, directory, budget, timeout, agent_model)
                status = result.get('status')
                entry.update(state='done' if status in (None, 'generated') else status, result=result, signature=signature(root, job))
            except KeyboardInterrupt:
                entry.update(state='uncertain' if job['action'] in {'inspect_runninghub', 'generate_runninghub'} else 'failed', reason='interrupted; inspect original effects before recovery')
                save_state(root, state)
                raise
            except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
                entry.update(state='uncertain' if job['action'] in {'inspect_runninghub', 'generate_runninghub'} else 'failed', reason=str(error))
            entry['finished_at'] = datetime.now().astimezone().isoformat()
            save_state(root, state)
            outcomes.append({'id': job['id'], **entry})
        # Dashboard refresh is a projection, independent from external job success.
        result = subprocess.run([sys.executable, str(root / 'queue/build_board.py')], cwd=root, capture_output=True, text=True, encoding='utf-8')
        if result.returncode:
            raise ValueError('jobs saved, but dashboard refresh failed: ' + result.stderr[-1000:])
    return outcomes


def recover(root, jobs, job_id, acknowledged):
    if not acknowledged:
        raise ValueError('use --acknowledge-after-inspection only after inspecting the original task/browser; this is not new spend authorization')
    if job_id not in {j['id'] for j in jobs}:
        raise ValueError('unknown job')
    with RunLock(root / '.private/automation/runner.lock'):
        state = read_state(root)
        previous = state['jobs'].get(job_id)
        if not previous:
            raise ValueError('job has no prior run to recover')
        history = state.setdefault('recoveries', [])
        history.append({'id': job_id, 'previous': previous, 'at': datetime.now().astimezone().isoformat()})
        del state['jobs'][job_id]
        save_state(root, state)


def recover_lock(root):
    folder = root / '.private/automation/runner.lock'
    owner = json.loads((folder / 'owner.json').read_text(encoding='utf-8'))
    if owner['host'] != socket.gethostname():
        raise ValueError('lock belongs to another host; inspect it there')
    if os.name == 'nt':
        import ctypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.restype = ctypes.c_void_p
        handle = api.OpenProcess(0x1000, False, owner['pid'])
        if handle:
            api.CloseHandle.argtypes = [ctypes.c_void_p]
            api.CloseHandle(handle)
            raise ValueError('owner process still exists; lock retained')
        if ctypes.get_last_error() != 87:
            raise ValueError('cannot verify lock owner; lock retained')
        (folder / 'owner.json').unlink()
        folder.rmdir()
        return
    try:
        os.kill(owner['pid'], 0)
    except ProcessLookupError:
        (folder / 'owner.json').unlink()
        folder.rmdir()
    else:
        raise ValueError('owner process still exists or cannot be verified; lock retained')


def doctor(root, browser=False):
    checks = [ {'name': 'python', 'ok': sys.version_info >= (3, 10), 'detail': sys.version.split()[0]},
        {'name': 'frontend', 'ok': all((root / 'queue' / n).is_file() for n in ('board.bundle.js', 'board.bundle.css')), 'detail': 'bundled JS/CSS'},
        {'name': 'records', 'ok': True, 'detail': 'PyYAML ' + yaml.__version__} ]
    try:
        ZoneInfo(read_mapping(root / 'queue/index.yaml').get('timezone', 'Asia/Shanghai'))
        jobs_from(root)
    except (ValueError, OSError, KeyError) as error:
        checks.append({'name': 'configuration', 'ok': False, 'detail': str(error)})
    else:
        checks.append({'name': 'configuration', 'ok': True, 'detail': 'timezone and job dependencies valid'})
    if browser:
        for name in ('ego-browser', 'codex'):
            command = shutil.which(name)
            checks.append({'name': name, 'ok': command is not None, 'detail': command or ('Install Ego Lite https://lite.ego.app/' if name == 'ego-browser' else 'Install Codex CLI and sign in')})
        if shutil.which('codex'):
            supported = subprocess.run(['codex', 'exec', '--help'], capture_output=True, text=True, encoding='utf-8', timeout=15)
            flags = ('--output-schema', '--ephemeral', '--sandbox', '--output-last-message')
            checks.append({'name': 'Codex CLI contract', 'ok': supported.returncode == 0 and all(f in supported.stdout for f in flags), 'detail': 'Required exec flags: ' + ', '.join(flags)})
            auth = subprocess.run(['codex', 'login', 'status'], capture_output=True, text=True, encoding='utf-8', timeout=15)
            checks.append({'name': 'Codex login', 'ok': auth.returncode == 0, 'detail': 'signed in' if auth.returncode == 0 else 'Run codex login interactively'})
        if shutil.which('ego-browser'):
            try:
                probe = subprocess.run(['ego-browser', 'nodejs'], input='console.log("AIGC_RUNTIME_OK");\n', text=True, encoding='utf-8', capture_output=True, timeout=15)
                ok = probe.returncode == 0 and 'AIGC_RUNTIME_OK' in (probe.stdout + probe.stderr)
                checks.append({'name': 'Ego connection', 'ok': ok, 'detail': 'connected' if ok else 'Open Ego Lite and complete onboarding'})
            except (OSError, subprocess.TimeoutExpired):
                checks.append({'name': 'Ego connection', 'ok': False, 'detail': 'Ego runtime unavailable'})
        skill_candidates = [Path.home() / '.agents/skills/ego-browser/SKILL.md', Path.home() / '.codex/skills/ego-browser/SKILL.md']
        checks.append({'name': 'ego-browser Skill', 'ok': any(p.is_file() for p in skill_candidates), 'detail': 'Install the official Ego Skill in ~/.agents/skills or ~/.codex/skills'})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['doctor', 'run', 'watch', 'status', 'recover', 'recover-lock', 'probe-agent'])
    parser.add_argument('--jobs', default='queue/automation.yaml', help='workspace-relative job configuration')
    parser.add_argument('--job', help='select one job; required for paid generation')
    parser.add_argument('--execute', action='store_true', help='actually execute; otherwise prints a plan')
    parser.add_argument('--point-budget', type=int, default=0, help='current user authorization for ONE selected generation job')
    parser.add_argument('--timeout', type=int, default=1800, help='maximum agent run seconds')
    parser.add_argument('--interval', type=int, default=30, help='foreground watch polling seconds (>=5)')
    parser.add_argument('--agent-model', help='model supported by YOUR Codex CLI account (required for generation/probe)')
    parser.add_argument('--browser', action='store_true', help='doctor: include optional browser/agent dependencies')
    parser.add_argument('--acknowledge-after-inspection', action='store_true')
    args = parser.parse_args()
    try:
        if args.timeout <= 0 or args.interval < 5 or args.point_budget < 0:
            raise ValueError('timeout > 0, interval >= 5, point-budget >= 0 required')
        if args.command == 'doctor':
            checks = doctor(ROOT, args.browser)
            print(json.dumps(checks, ensure_ascii=False, indent=2))
            return 0 if all(c['ok'] for c in checks) else 1
        if args.command == 'probe-agent':
            if not args.agent_model:
                raise ValueError('probe-agent requires --agent-model from your CLI model list')
            directory = ROOT / '.private/automation/agent-smoke'
            directory.mkdir(parents=True, exist_ok=True)
            schema, output = directory / 'schema.json', directory / 'result.json'
            atomic_text(schema, json.dumps({'type': 'object', 'additionalProperties': False, 'required': ['runtime'], 'properties': {'runtime': {'type': 'string', 'enum': ['ready']}}}))
            output.unlink(missing_ok=True)
            invoke_agent(ROOT, 'CLI transport smoke test: do not use tools, edit files or open a browser. Return {"runtime":"ready"} as the entire final response.', schema, output, directory, min(args.timeout, 60), agent_model=args.agent_model)
            if json.loads(output.read_text(encoding='utf-8')) != {'runtime': 'ready'}:
                raise ValueError('unexpected agent probe result')
            print('Codex agent transport ready. This does not verify RunningHub generation.')
            return 0
        jobs = jobs_from(ROOT, args.jobs)
        if args.job and args.job not in {j['id'] for j in jobs}:
            raise ValueError('unknown --job')
        if args.command == 'recover':
            recover(ROOT, jobs, args.job, args.acknowledge_after_inspection)
            print('Recovery recorded; original browser binding retained.')
            return 0
        if args.command == 'recover-lock':
            recover_lock(ROOT)
            print('Abandoned lock removed; interrupted jobs still require inspection/recover.')
            return 0
        if args.command == 'watch' and (args.point_budget or (args.job and next(j for j in jobs if j['id'] == args.job)['action'] == 'generate_runninghub')):
            raise ValueError('watch supports preparation/inspection only; run one paid job explicitly in its window')
        if args.command in {'status', 'watch'} or not args.execute:
            rows = plan(ROOT, jobs, read_state(ROOT))
            print(json.dumps(rows, ensure_ascii=False, indent=2), flush=True)
            if args.command != 'watch' or not args.execute:
                return 0
        previous_outcomes = None
        while True:
            outcomes = execute(ROOT, jobs, args.job, args.point_budget, args.timeout, args.agent_model)
            if outcomes != previous_outcomes:
                print(json.dumps(outcomes, ensure_ascii=False, indent=2), flush=True)
                previous_outcomes = outcomes
            if args.command != 'watch':
                return 1 if any(r['state'] not in {'done', 'disabled'} for r in outcomes) else 0
            time.sleep(args.interval)
            jobs = jobs_from(ROOT, args.jobs)
    except KeyboardInterrupt:
        print('Stopped; inspect status before recovery.', file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
