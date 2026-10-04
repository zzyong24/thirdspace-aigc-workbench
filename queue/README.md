# 制作队列与工作台

安装根目录 requirements.txt 后，运行 `python3 queue/serve_board.py`，打开 <http://127.0.0.1:8767/queue/board.html>。`--port` 可换端口；Ctrl+C 停止。静态页面与本地素材同源，便于阅读文档和预览。

工作台显示构建时快照，包含作品总览、进度、资料、素材、镜头引用、提示词和文件台账；它不会自行执行任务、监控浏览器或创建 Codex 自动化。顶栏显示的是配置记录，无法证明任何定时器真实在运行。

- `index.yaml`：时区、积分通道时间、模型、预算与执行策略。
- `anytime.yaml`：输入/依赖就绪后可准备的任务；外部新增费用仍需授权。
- `points-21.yaml`：需要积分的任务；名称保留兼容，实际时间以 index.yaml 为准。

新安装默认不授权积分、不配置自动化，模型、价格、免费窗口和并发必须在 RunningHub 现场核实。配置允许积分只是偏好，不代替当前用户授权。调度器由使用者单独配置；本仓库不安装任何定时任务。

状态：`intake → preparing → ready → running → review → editing → exporting_to_canvas → done`。受阻时使用 `waiting_input`、`waiting_dependency`、`waiting_browser`、`waiting_balance` 或 `retry_needed`。已经完成的返工任务不应再计入待返工数。

修改 YAML 后先渲染项目文档，再执行 `python3 queue/build_board.py`，刷新浏览器。仅 Markdown 的旧项目支持原有固定章节/表格；新项目使用 docs/records.md 中的版本化记录。修改界面时进入 `queue/board-ui/` 执行 `npm ci` 和 `npm run build`，然后重新生成页面。
