#!/usr/bin/env python3
"""Build a self-contained data page for the local Ant Design production board."""

from __future__ import annotations
import sys


import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from project_records import load_project, board_records
from storage import within, atomic_text


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "queue"
PROJECTS = ROOT / "projects"
DOCUMENT_SPECS = (
    ("project.yaml", "作品元信息", "规范"),
    ("AGENTS.md", "项目说明", "规范"),
    ("proposal.md", "创意方案", "策划"),
    ("research.md", "研究资料", "策划"),
    ("script.md", "剧本", "创作"),
    ("storyboard.md", "分镜脚本", "创作"),
    ("project_assets.md", "项目资产索引", "资产"),
    ("assets/asset-matrix.md", "三视图资产矩阵", "资产"),
    ("prompts/shot-prompts.md", "逐镜生成计划与提示词", "生成"),
    ("shot_audit.md", "逐镜审片记录", "生成"),
    ("assets/asset-matrix.yaml", "资产数据（维护源）", "资产"),
    ("prompts/shots.yaml", "镜头数据（维护源）", "生成"),
    ("shot_audit.yaml", "审片数据（维护源）", "生成"),
    ("assets/audio/source.yaml", "音源与授权记录", "音频"),
)


def file_entry(path: Path, category: str, title: str = "") -> dict:
    within(ROOT, path.relative_to(ROOT).as_posix())
    stat = path.stat()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "name": path.name,
        "title": title or path.name,
        "category": category,
        "bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, ZoneInfo("Asia/Shanghai")).isoformat(timespec="minutes"),
        "version": (match.group(1) if (match := re.search(r"(?:^|[-_])v(\d+)(?:[._-]|$)", path.name, re.I)) else ""),
    }


def document_items(folder: Path) -> list[dict]:
    items = []
    for relative, title, category in DOCUMENT_SPECS:
        path = within(folder, relative)
        item = {"key": relative, "title": title, "category": category, "exists": path.is_file(), "content": ""}
        if path.is_file():
            item.update(file_entry(path, category, title))
            item["content"] = read_text(path)
        items.append(item)
    known = {relative for relative, _, _ in DOCUMENT_SPECS}
    for path in sorted(folder.rglob("*.md")):
        relative = path.relative_to(folder).as_posix()
        if relative in known or any(part.startswith(".") for part in path.relative_to(folder).parts) or not path.resolve().is_relative_to(folder.resolve()):
            continue
        category = "资产提示词" if relative.startswith("prompts/assets/") else "附加文档"
        title = f"资产提示词 · {path.stem}" if category == "资产提示词" else relative
        items.append({
            **file_entry(path, category, title),
            "key": relative,
            "exists": True,
            "content": read_text(path),
        })
    return items


def workspace_documents() -> list[dict]:
    items = []
    for relative, title in (
        ("queue/README.md", "队列说明"),
        ("projects/AGENTS.md", "作品目录规范"),
        ("projects/FILE_RULES.md", "文件命名与存放规则"),
        (".agents/skills/runninghub-minimax-story-video/SKILL.md", "RunningHub 视频操作 Skill"),
        (".agents/skills/runninghub-minimax-story-video/references/runninghub-operations.md", "RunningHub 操作经验与故障处理"),
    ):
        path = ROOT / relative
        if path.is_file():
            content = read_text(path)
            if path.name == "SKILL.md":
                # Skill metadata is for the agent loader, not the Markdown reader.
                content = re.sub(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", "", content, count=1, flags=re.S).lstrip()
            items.append({
                **file_entry(path, "工作区规范", title),
                "key": relative,
                "exists": True,
                "content": content,
            })
    return items


def inventory(folder: Path, extras: list[Path] | None = None) -> list[dict]:
    files = [path for path in folder.rglob("*") if path.is_file() and path.resolve().is_relative_to(folder.resolve()) and not any(part.startswith(".") for part in path.relative_to(folder).parts)]
    files.extend(path for path in (extras or []) if path.is_file() and path not in files)
    items = []
    for path in files:
        relative = path.relative_to(folder).as_posix() if path.is_relative_to(folder) else ""
        if relative.startswith("assets/characters/"):
            category = "人物图像"
        elif relative.startswith("assets/scenes/"):
            category = "场景图像"
        elif relative.startswith("assets/props/"):
            category = "道具图像"
        elif relative.startswith("assets/audio/"):
            category = "音频与授权"
        elif relative.startswith("prompts/"):
            category = "提示词"
        elif relative.startswith("generated/shots/") or path.suffix.lower() in {".mp4", ".mov"}:
            category = "分镜视频"
        elif relative.startswith("exports/"):
            category = "成片与工程"
        elif path.suffix.lower() == ".png":
            category = "过程截图 / 参考图"
        elif path.suffix.lower() in {".md", ".yaml", ".yml"}:
            category = "项目文档"
        else:
            category = "其他文件"
        items.append(file_entry(path, category))
    return sorted(items, key=lambda item: (item["category"], item["path"]))


def git_snapshot() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return ""
    commits = []
    for line in git("log", "-8", "--pretty=format:%h%x09%s%x09%cI").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            commits.append(dict(zip(("hash", "subject", "date"), parts)))
    return {"enabled": bool(git("rev-parse", "--is-inside-work-tree")), "head": git("rev-parse", "--short", "HEAD"), "branch": git("branch", "--show-current"), "commits": commits}


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def shot_records(project_path: Path) -> list[dict]:
    text = read_text(project_path / "shot_audit.md")
    pattern = re.compile(r"^\|\s*(\d{1,3})\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", re.M)
    shots = []
    for match in pattern.finditer(text):
        number, duration, verdict, notes = (part.strip() for part in match.groups())
        state = "redo" if "需重做" in verdict else "passed" if "通过" in verdict else "review"
        shots.append({
            "number": int(number),
            "duration": duration,
            "verdict": verdict,
            "state": state,
            "notes": notes,
        })
    return shots


def expected_shots(project_path: Path, actual_count: int) -> int:
    plan = read_text(project_path / "prompts/shot-prompts.md")
    numbers = [int(n) for n in re.findall(r"^###\s+(\d{1,3})\s*[·.]", plan, re.M)]
    return max(max(numbers, default=0), actual_count)


def asset_summary(project_path: Path) -> dict:
    text = read_text(project_path / "assets/asset-matrix.md")
    counts = {"total": 0, "characters": 0, "scenes": 0, "props": 0, "canvas_nodes": 0, "uploaded": 0}
    items, _ = project_assets(project_path)
    category_keys = {"人物": "characters", "场景": "scenes", "道具": "props"}
    for item in items:
        if item["image"] and not item["historical"]:
            counts["total"] += 1
            counts[category_keys[item["category"]]] += 1
            counts["uploaded"] += int(item.get("uploaded", False))
    # Canvas node counts are observational; never infer upload from a local image.
    match = re.search(r"当前共 (\d+) 个参考节点", text)
    if match:
        counts["canvas_nodes"] = int(match.group(1))
    return counts


def project_assets(project_path: Path) -> tuple[list[dict], dict[int, list[str]]]:
    """Read the project's asset register and its storyboard coverage notes."""
    source = project_path / "assets/asset-matrix.md"
    records = load_project(project_path)
    if records is not None:
        items, coverage, _, _ = board_records(project_path, ROOT, records)
        return items, coverage
    text = read_text(source)
    assets: list[dict] = []
    by_shot: dict[int, list[str]] = {}
    section = ""
    in_coverage = False
    categories = {"人物": "人物", "场景": "场景", "物件": "道具"}
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)", line)
        if heading:
            section = heading.group(1).strip()
            in_coverage = section == "分镜覆盖核对"
            continue
        if section in categories and re.match(r"^\|\s*[CSP]\d{2}\s*\|", line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            asset_id, name, shots, image_cell, prompt_cell, status = cells[:6]
            image_match = re.search(r"`([^`]+\.png)`", image_cell)
            prompt_match = re.search(r"`([^`]+\.md)`", prompt_cell)
            image = source.parent / image_match.group(1) if image_match else None
            prompt = project_path / prompt_match.group(1) if prompt_match else None
            assets.append({
                "id": asset_id, "category": categories[section], "name": name,
                "shots": shots, "status": status, "historical": shots == "—", "uploaded": bool(re.search(r"已.*上传", status)),
                "image": image.relative_to(ROOT).as_posix() if image and image.exists() else "",
                "image_name": image_match.group(1) if image_match else "",
                "prompt_file": prompt.relative_to(ROOT).as_posix() if prompt and prompt.exists() else "",
            })
        if in_coverage:
            match = re.match(r"^-\s*(\d{2})(?:[–—-](\d{2}))?：(.+)$", line)
            if not match:
                continue
            start, end, detail = match.groups()
            base_detail = re.sub(r"（[^）]*另接[^）]*）", "", detail)
            ids = list(dict.fromkeys(re.findall(r"\b[CSP]\d{2}\b", base_detail)))
            for number in range(int(start), int(end or start) + 1):
                by_shot[number] = ids.copy()
            for extra in re.finditer(r"（(\d{2})(?:[–—-](\d{2}))?\s*另接\s*([CSP]\d{2})）", detail):
                first, last, asset_id = extra.groups()
                for number in range(int(first), int(last or first) + 1):
                    by_shot[number] = list(dict.fromkeys([*by_shot.get(number, []), asset_id]))
    return assets, by_shot


def project_prompts(project_path: Path, assets: list[dict], coverage: dict[int, list[str]]) -> list[dict]:
    text = read_text(project_path / "prompts/shot-prompts.md")
    filename_ids = {Path(item["image_name"]).name: item["id"] for item in assets if item["image_name"]}
    filename_paths = {Path(item["image_name"]).name: ROOT / item["image"] for item in assets if item["image"]}
    asset_paths = {item["id"]: ROOT / item["image"] for item in assets if item["image"]}
    sections = re.split(r"(?=^###\s+\d{1,3}\s*·)", text, flags=re.M)
    prompts = []
    for section in sections:
        heading = re.search(r"^###\s+(\d{1,3})\s*·\s*(.+)$", section, re.M)
        if not heading:
            continue
        number = int(heading.group(1))
        reference_match = re.search(r"^参考：(.+)$", section, re.M)
        references = re.findall(r"`([^`]+)`", reference_match.group(1)) if reference_match else []
        prompt_match = re.search(r"^提示词：([\s\S]*?)(?=\n\s*\n|\Z)", section, re.M)
        reference_details = []
        for name in references:
            asset_id = filename_ids.get(name) or next(
                (item["id"] for item in assets if Path(item["image_name"]).name.startswith(name) or re.sub(r"-v\d+(?=\.)", "", Path(item["image_name"]).name) == re.sub(r"-v\d+(?=\.)", "", name)), ""
            )
            image_file = filename_paths.get(name)
            if not image_file and asset_id in asset_paths:
                image_file = asset_paths[asset_id].with_name(name)
            reference_details.append({
                "name": name, "asset_id": asset_id,
                "image": image_file.relative_to(ROOT).as_posix() if image_file and image_file.exists() else "",
            })
        actual_ids = list(dict.fromkeys(detail["asset_id"] for detail in reference_details if detail["asset_id"]))
        prompts.append({
            "number": number, "title": heading.group(2).strip(),
            "text": prompt_match.group(1).strip() if prompt_match else "",
            "references": references,
            "reference_details": reference_details,
            "reference_asset_ids": actual_ids,
            "planned_asset_ids": coverage.get(number, []),
        })
    return prompts


def legacy_storyboards() -> dict[int, dict]:
    source = ROOT / "generated/runninghub-minimax-pets/storyboards-v2.md"
    result = {}
    for section in re.split(r"(?=^##\s+\d{2}\s+)", read_text(source), flags=re.M):
        heading = re.search(r"^##\s+(\d{2})\s+(.+)$", section, re.M)
        if not heading:
            continue
        reference = re.search(r"^角色参考：`([^`]+)`", section, re.M)
        shots = []
        for match in re.finditer(r"^([1-3])\.\s+\*\*(.+?)\*\*：(.+)$", section, re.M):
            shots.append({
                "number": int(match.group(1)), "title": match.group(2),
                "text": match.group(3).strip(),
                "references": [reference.group(1)] if reference else [],
                "reference_details": [{"name": reference.group(1), "asset_id": "REF01", "image": ""}] if reference else [],
                "reference_asset_ids": ["REF01"] if reference else [],
                "planned_asset_ids": ["REF01"] if reference else [],
            })
        result[int(heading.group(1))] = {
            "source": source.relative_to(ROOT).as_posix(),
            "reference": reference.group(1) if reference else "",
            "shots": shots,
            "body": section.strip(),
        }
    return result


def collect_projects(anytime: dict, points: dict) -> list[dict]:
    entries: dict[str, dict] = {}
    if PROJECTS.exists():
        for folder in PROJECTS.iterdir():
            if folder.is_dir() and folder.resolve().is_relative_to(PROJECTS.resolve()) and (folder / "AGENTS.md").exists():
                relative = folder.relative_to(ROOT).as_posix()
                entries[relative] = {"anytime": [], "points_21": []}
    for lane_name, lane in (("anytime", anytime), ("points_21", points)):
        for item in lane.get("items", []):
            relative = item["project"]
            entries.setdefault(relative, {"anytime": [], "points_21": []})[lane_name].append(item)

    projects = []
    for relative, tasks in entries.items():
        folder = within(PROJECTS, relative.removeprefix('projects/'))
        if folder.parent.resolve() != PROJECTS.resolve():
            raise ValueError('queued projects must be direct children of projects/')
        metadata = read_yaml(folder / "project.yaml")
        guide = read_text(folder / "AGENTS.md")
        heading = re.search(r"^#\s+(.+)$", guide, re.M)
        task_title = next(
            (items[0]["title"] for items in (tasks["points_21"], tasks["anytime"]) if items and items[0].get("title")),
            None,
        )
        records = load_project(folder)
        if records is not None:
            asset_items, coverage, prompts, shots = board_records(folder, ROOT, records)
        else:
            shots = shot_records(folder)
            asset_items, coverage = project_assets(folder)
            prompts = project_prompts(folder, asset_items, coverage)
        passed = sum(shot["state"] == "passed" for shot in shots)
        redo = sum(shot["state"] == "redo" for shot in shots)
        retakes = sorted({number for item in tasks["points_21"] if item.get("state") != "done" for number in item.get("shots", [])})
        assets = asset_summary(folder)
        final_waiting = any(item.get("task") == "final_online_edit" for item in tasks["anytime"])
        if retakes:
            stage = "分镜返工待执行"
        elif redo:
            stage = "分镜待返工"
        elif shots and passed == len(shots):
            stage = "审片通过"
        elif any(shot["state"] in {"generated", "review"} for shot in shots):
            stage = "逐镜审核中"
        elif assets["total"]:
            stage = "资产已登记"
        else:
            stage = "前期准备"
        first_task = (tasks["points_21"] or tasks["anytime"] or [{}])[0]
        projects.append({
            "kind": "project",
            "title": metadata.get("title") or task_title or (heading.group(1) if heading else folder.name),
            "path": relative,
            "canvas": metadata.get("canvas_url") or first_task.get("canvas", ""),
            "stage": {"intake": "待准备", "preparing": "前期准备", "ready": "就绪；待现场核验", "running": "生成中", "review": "逐镜审核中", "editing": "剪辑中", "exporting_to_canvas": "正在导出到画布", "done": "已完成"}.get(metadata.get("status"), stage) if records is not None else stage,
            "shot_count": len(shots),
            "generated": sum(shot["state"] in {"generated", "review", "passed", "redo"} for shot in shots),
            "expected_shots": len(records["shots"]) if records is not None else expected_shots(folder, len(shots)),
            "passed": passed,
            "redo": redo,
            "shots": shots,
            "retake_numbers": retakes,
            "assets": assets,
            "asset_items": asset_items,
            "shot_prompts": prompts,
            "audio": read_yaml(folder / "assets/audio/source.yaml"),
            "anytime": tasks["anytime"],
            "points_21": tasks["points_21"],
            "final_waiting": final_waiting,
            "documents": {
                name: (folder / name).exists()
                for name in ("AGENTS.md", "research.md", "script.md", "storyboard.md", "prompts/shot-prompts.md", "shot_audit.md")
            },
            "document_items": document_items(folder),
            "inventory": inventory(folder),
            "story_file": "",
            "reference_image": "",
        })
    projects.extend(collect_legacy_works())
    projects.sort(key=lambda item: (item["kind"] != "project", -int(bool(item["anytime"] or item["points_21"])), item["title"]))
    return projects


def collect_legacy_works() -> list[dict]:
    """Expose the ten existing pet story samples without claiming they were audited."""
    base = ROOT / "generated/runninghub-minimax-pets"
    source = base / "README.md"
    works = []
    storyboards = legacy_storyboards()
    row = re.compile(r"^\|\s*(\d{1,2})\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|")
    for line in read_text(source).splitlines():
        match = row.match(line)
        if not match:
            continue
        number, title, shot_cell, canvas_cell = match.groups()
        index = int(number)
        links = re.findall(r"\[(\d{2})\]\(([^)]+)\)", shot_cell)
        if not links:
            continue
        folder = base / Path(links[0][1]).parent
        shots = []
        for shot_number, relative_file in links:
            shot_file = base / relative_file
            shots.append({
                "number": int(shot_number),
                "duration": "约 5 秒",
                "verdict": "已生成，未登记逐镜审片",
                "state": "generated" if shot_file.exists() else "missing",
                "notes": shot_file.stem.replace("-", " "),
                "file": shot_file.relative_to(ROOT).as_posix(),
            })
        current_story = (
            base / "storyworks/10-guinea-pigs/story.mp4"
            if index == 10
            else folder / "story.mp4"
        )
        assembled = index in (*range(1, 8), 10) and current_story.exists()
        canvas_match = re.search(r"\[RunningHub 画布\]\((https?://[^)]+)\)", canvas_cell)
        image_match = re.search(r"\[画布截图\]\(([^)]+)\)", canvas_cell)
        reference_image = (base / image_match.group(1)).relative_to(ROOT).as_posix() if image_match else ""
        storyboard = storyboards.get(index, {})
        local_reference = folder / "reference.png"
        reference_asset = {
            "id": "REF01", "category": "角色参考", "name": "故事角色参考图",
            "shots": "01–03", "status": "历史样片参考；未登记完整三视图矩阵",
            "historical": False,
            "image": local_reference.relative_to(ROOT).as_posix() if local_reference.exists() else "",
            "image_name": storyboard.get("reference", ""), "prompt_file": "",
        }
        storyboard_shots = storyboard.get("shots", [])
        for shot in storyboard_shots:
            for detail in shot["reference_details"]:
                detail["image"] = reference_asset["image"]
        works.append({
            "kind": "archive",
            "title": title.strip(),
            "path": folder.relative_to(ROOT).as_posix(),
            "source_document": source.relative_to(ROOT).as_posix(),
            "canvas": canvas_match.group(1) if canvas_match else "",
            "stage": "已合成样片" if assembled else "待按新分镜重剪",
            "shot_count": len(shots),
            "expected_shots": len(links),
            "generated": sum(shot["state"] == "generated" for shot in shots),
            "passed": 0,
            "redo": 0,
            "shots": shots,
            "retake_numbers": [],
            "assets": {"total": 0, "characters": 0, "scenes": 0, "props": 0, "canvas_nodes": 0, "uploaded": 0},
            "asset_items": [reference_asset] if storyboard else [],
            "shot_prompts": storyboard_shots,
            "prompt_source": storyboard.get("source", ""),
            "audio": {},
            "anytime": [],
            "points_21": [],
            "final_waiting": False,
            "documents": {},
            "document_items": ([{
                **file_entry(ROOT / storyboard["source"], "创作", "历史样片分镜方案"),
                "key": "storyboard", "exists": True, "content": storyboard.get("body", ""),
            }] if storyboard else []) + [{
                **file_entry(source, "历史记录", "历史样片来源记录"),
                "key": "source", "exists": True, "content": read_text(source),
            }],
            "inventory": inventory(folder, [source, ROOT / storyboard["source"]] if storyboard else [source]),
            "story_file": current_story.relative_to(ROOT).as_posix() if assembled else "",
            "reference_image": reference_image,
        })
    return works


def main() -> None:
    index = read_yaml(QUEUE / "index.yaml")
    anytime = read_yaml(QUEUE / "anytime.yaml")
    points = read_yaml(QUEUE / "points-21.yaml")
    timezone = index.get("timezone", "Asia/Shanghai")
    board = {
        "timezone": timezone,
        "updated": datetime.now(ZoneInfo(timezone)).isoformat(timespec="minutes"),
        "automation_status": index.get("credit_queue_automation", "unknown"),
        "automation_id": index.get("credit_queue_automation_id", ""),
        "execution_policy": index.get("execution_policy", {}),
        "credit_start": index.get("credit_queue_check_start", "21:00"),
        "git": git_snapshot(),
        "workspace_documents": workspace_documents(),
        "projects": collect_projects(anytime, points),
    }
    data = json.dumps(board, ensure_ascii=False).replace("</", "<\\/")
    template = read_text(QUEUE / "board-ui/template.html")
    if "__BOARD_DATA__" not in template:
        raise ValueError("board-ui/template.html is missing the data slot")
    output = QUEUE / "board.html"
    atomic_text(output, template.replace("__BOARD_DATA__", data))
    print(f"Updated {output.relative_to(ROOT)} ({len(board['projects'])} project(s))")


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    main()
