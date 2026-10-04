# 记录格式 v1

新项目包含三个 YAML 维护源。字段错误会中止构建；Markdown 阅读页只由渲染脚本生成。完整例子在 `projects/demo-rooftop/`。

## 资产：assets/asset-matrix.yaml

```yaml
version: 1
assets:
  - id: C01
    category: character
    name: 机器人
    shots: [1, 2]
    image: characters/C01-robot-turnaround-v01.png
    prompt_file: prompts/assets/C01-robot.md
    status: draft
    historical: false
```

category 为 character / scene / prop；ID 分别以 C/S/P 开头，同一项目唯一。image 相对 assets/，prompt_file 相对项目根。status 为 draft / generated / uploaded；历史文件保留在磁盘与日志，矩阵维护当前版本。示意图保持 draft。

## 镜头：prompts/shots.yaml

```yaml
version: 1
shots:
  - id: 1
    title: 找到光
    duration_seconds: 5
    references: [C01]
    prompt: 角色在屋顶走向中央，保持身份、服装和空间布局。
    camera:
      start: 全景，南侧机位高1.2米，角色位于左侧。
      move: 0–3秒缓慢向右横移约半个角色身宽。
      stop: 3–5秒锁定，角色居中，全身与栏杆留在末帧。
      continuity: 保持向右行进，下一镜不跨轴。
    settings:
      model: MiniMax H3 RH Enhanced
      mode: 全能参考
      aspect_ratio: "9:16"
      resolution: 以当前UI为准
```

镜号为唯一正整数；时长是正数，需再次和 UI 支持的时长对照。references 使用资产 ID，按矩阵解析当前图片。资产覆盖与实际引用会在分镜用料页对照。系列作品建议逐集建立独立项目；v1 不支持 E01-01 这类复合镜号。

## 审片：shot_audit.yaml

```yaml
version: 1
records:
  - id: 1
    duration_seconds: 5
    state: planned
    notes: 尚未提交。
    video: ""
```

state 为 planned / running / generated / review / passed / redo；planned 和 running 不计入已生成或审片通过。notes 写实际观察，video 相对项目根目录，可为空（在线交付时另在 run-log.md 记录节点链接）。passed 是人工审片结论，schema 不会替你观看视频。

## 维护与验证

```bash
python3 projects/render_records.py projects/demo-rooftop
python3 projects/render_records.py projects/demo-rooftop --check
python3 projects/render_records.py projects/demo-rooftop --check --ready
python3 queue/build_board.py
```

示例的 --ready **应失败**，因为图像为 draft、未上传。真实作品只有在正式参考图存在、标记已上传、镜头提示词与四项摄影调度齐备后才能通过。通过本地检查仍须核验真实上传、模型/参数、当前费用、预算及用户授权。

未知资产、镜号重复、未知版本、无效时长、越界路径或符号链接指向项目外会报错。仅 Markdown 的旧项目保留兼容读取；迁移时参照新字段建 YAML，再确认工作台的资产数量、引用和审片状态。
