#!/usr/bin/env python3
"""Create a video project with the workspace's fixed asset layout."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "queue"))
from project_records import render_markdown


PROJECTS = Path(__file__).resolve().parent
DIRECTORIES = (
    "assets/characters",
    "assets/scenes",
    "assets/props",
    "assets/audio",
    "prompts/assets",
    "generated/shots",
    "exports",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="lowercase project folder name, e.g. spring-story")
    parser.add_argument("--title", required=True, help="user-facing work title")
    args = parser.parse_args()
    if len(args.slug) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug) or args.slug in {'con', 'prn', 'aux', 'nul', *(f'com{n}' for n in range(1,10)), *(f'lpt{n}' for n in range(1,10))}:
        parser.error("slug must use 1–64 lowercase letters/digits/hyphens and cannot be a Windows device name")
    title = args.title.strip()
    if not title:
        parser.error("title cannot be empty")

    folder = PROJECTS / args.slug
    try:
        folder.mkdir(exist_ok=False)
    except OSError as error:
        parser.error(f'cannot create project: {error}')
    for relative in DIRECTORIES:
        (folder / relative).mkdir(parents=True)
    documents = {
        "project.yaml": f"""id: {args.slug}
title: {json.dumps(title, ensure_ascii=False)}
kind: video
status: preparing
aspect_ratio: "9:16"
target_duration_seconds: null
delivery_mode: undecided
canvas_url: null
""",
        "AGENTS.md": f"""# {title} · 项目说明

遵循上级 `../AGENTS.md` 的固定目录、资产矩阵、三视图和生成规则。

## 项目目标与阶段

- 作品：{title}
- 阶段：前期准备
- 画布：待建立；本作品单独使用一张 RunningHub 画布。

## 工作入口

- 先写 `proposal.md`、`research.md`、`script.md`；在 `prompts/shots.yaml` 维护分镜和摄影调度。
- 在 `assets/asset-matrix.yaml` 与 `shot_audit.yaml` 维护资产和审片；运行 `projects/render_records.py` 生成 Markdown 阅读页，勿直接编辑生成页。
- RunningHub 网页操作使用 `../../.agents/skills/runninghub-minimax-story-video/SKILL.md`，浏览器操作遵循 `$ego-browser`。
- 在 `project_assets.md` 记录资产路径、音源状态、画布链接与交付物；项目特有约束补在本文件。
""",
        "proposal.md": f"# {title} · 创意方案\n\n阶段：待研究与设计。\n",
        "research.md": f"# {title} · 研究记录\n\n按事实来源、听众解读和创作选择分别记录。\n",
        "project_assets.md": f"# {title} · 项目资产索引\n\n尚未登记资产。按 `../AGENTS.md` 的固定目录放置并维护资产矩阵。\n",
        "script.md": f"# {title} · 剧本\n\n阶段：草稿。\n",
        "storyboard.md": f"# {title} · 分镜\n\n逐镜记录时长、人物、场景、道具、动作、机位和声音。\n",
        "assets/asset-matrix.yaml": "version: 1\nassets: []\n",
        "prompts/shots.yaml": "version: 1\nshots: []\n",
        "shot_audit.yaml": "version: 1\nrecords: []\n",
        "assets/audio/source.yaml": "source: null\nfile_status: missing\nlicense_status: unverified\n",
        "run-log.md": "# 运行记录\n\n尚未提交任何生成任务。每次记录节点、版本、费用、任务状态和首/中/尾审片结果。\n",

    }
    for name, content in documents.items():
        (folder / name).write_text(content, encoding="utf-8")
    render_markdown(folder)
    print(folder)


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    main()
