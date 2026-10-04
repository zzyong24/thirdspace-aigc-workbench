# 验证记录

2026-10-05，作者侧代理自测。此文件区分代码回归与真实外部流程，不将单元测试当作视频生成成功。

## 当前通过

- 37 项 Python 单元/集成测试：陌生中文空格路径的实际 CLI、新作品脚手架、Skill 独立安装、严格 YAML、缺图/草稿/摄影调度、依赖拓扑与变化、幂等执行、写前状态、中断/超时不重试、显式恢复、并发锁、积分授权/时区窗口、结果证据契约、原子写失败保留旧文件、Windows 路径/保留名、本地 HTTP 隐藏文件/外链隔离。
- 实际执行 render → 刷新 board，再运行会跳过相同输入。check_ready 对教学草稿失败是预期行为。
- Ego Lite 真实 Chromium：39 项检查覆盖 1440/768/390px 的进度、资料、资产、用料、提示词、文件页、图片加载、无页面横向溢出、窄屏菜单开关与空搜索。执行命令：scripts/check_ui.py。视口模拟是布局验收，不等于 iPhone/Android 实机测试。
- 真实 RunningHub 首页观察通过执行器运行，保存了 Ego spaceId、真实 URL 与 snapshot；没有点击生成或消费积分。修复了 Ego console 写 stderr 和自定义环境变量不透传的问题，加入回归。
- 真实 Codex CLI 0.144.5 结构化输出探测通过；发现桌面模型别名不能用于 CLI，改为显式 --agent-model。仅证明实际模型调用链路，不证明 RunningHub 动作。
- npm 生产构建、Ant Design CLI lint（0问题）。

## 持续集成

工作流现在运行 Python 3.10/3.13 × Ubuntu/macOS/Windows 六组，以及 Node20/22 两组前端构建。实际结果以 [GitHub Actions](https://github.com/zzyong24/thirdspace-aigc-workbench/actions/workflows/ci.yml) 对当前提交的状态为准。

Windows无创建符号链接权限时，只跳过对应符号链接用例，其余HTTP/路径测试仍运行。Ego 官方当前提供Mac版，所以不会把Windows/Linux的Python CI描述为浏览器生成验收。

## 仍未验证

实验性 generate_runninghub 尚未以指定作品完成“上传/引用 → 现场核价 → 提交 → 等待 → 可播放结果 → 审片登记 → 中断恢复”的端到端实机验收。依赖自己的平台账号、既有画布、当前模型、正确资产及本次预算；未通过前不发布为稳定生成能力。

不同 RunningHub 语言/账号套餐、UI改版、登录/CAPTCHA交接、长视频在线剪辑与导出、其他代理宿主、手机硬件均未完成全面兼容验收。运行锁和结果校验无法替平台保证费用/生成质量，代理必须现场核对。

## v0.1.0 基线

2026-10-04 的12项测试、带空格陌生目录的全新Git克隆/隔离venv/官方PyPI与npm安装、HTTP服务、真实示例资产/Skill阅读、Gitleaks树与新历史扫描均通过。旧版Ubuntu Python3.11/Node22 CI：[验证记录](https://github.com/zzyong24/thirdspace-aigc-workbench/actions/runs/37209446711)。原生产工作区、账户日志和真实作品未复制到公开仓库。
