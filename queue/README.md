# 制作队列与执行器

安装根目录 requirements.txt 后，运行 `python3 queue/serve_board.py`，打开 <http://127.0.0.1:8767/queue/board.html>。端口可配置；Ctrl+C 停止。工作台是数据快照，更新记录或执行任务后刷新浏览器。

- index.yaml：时区、积分窗口、模型和预算策略。
- anytime.yaml / points-21.yaml：制作计划台账，文字依赖供人和代理阅读。
- automation.yaml：执行器的严格任务契约，ID依赖供机器校验，不能填写任意 shell。
- .private/automation/：真实执行状态、锁和浏览器绑定，既不提交Git也不由HTTP提供。

```bash
python3 queue/automation.py doctor
python3 queue/automation.py run
python3 queue/automation.py run --execute
python3 queue/automation.py status
python3 queue/automation.py watch --execute
```

run 默认仅打印计划；--execute 才执行。watch 是前台持续准备进程，不是系统调度器；不批量消费积分。未完成任务和改变的依赖阻止后续执行；浏览器超时需要先检查原任务再恢复。

默认仅启用原创教学例子的 render。SVG参考是草稿，镜头是planned；不能把教学例子或配置 true 当作真实上传/付款/完成证据。实验性生成入口、外部依赖、模型适配和完整恢复说明见 [自动化手册](../docs/automation.md)。

制作状态仍由项目记录维护：intake → preparing → ready → running → review → editing → exporting_to_canvas → done。执行器中 job done 只表示这一动作完成，不等于整部作品完成。

界面源代码在 board-ui/。修改后 npm ci、npm run build，再 python3 queue/build_board.py；YAML始终是记录事实来源。
