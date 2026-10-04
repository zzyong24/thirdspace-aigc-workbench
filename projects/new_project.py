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
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        parser.error("slug must use lowercase letters, digits and hyphens")
    title = args.title.strip()
    if not title:
        parser.error("title cannot be empty")

    folder = PROJECTS / args.slug
    folder.mkdir(exist_ok=False)
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

- 先写 `proposal.md`、`research.md`、`script.md`、`storyboard.md`。
- 生成前建立 `assets/asset-matrix.md` 与 `prompts/shot-prompts.md`，核对全部人物、场景、道具及每镜引用。
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
    main()
