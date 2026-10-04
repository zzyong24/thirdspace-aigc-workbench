# 自动化使用手册

本仓库包含真实执行代码。**准备和浏览器观察已实测；生成适配器仍是实验功能，未完成真实视频任务验收。** 单元测试不会被当作平台生成成功的证据。

## 运行前准备

先按 README 安装 requirements.txt。进入仓库目录后执行 `python3 queue/automation.py doctor`。所有路径相对仓库根目录解析；脚本也可以从仓库外用绝对路径启动。Windows 使用 `python` 代替 `python3`。

| 能力 | 依赖 / 支持范围 |
|---|---|
| 工作台与准备任务 | Python 3.10+、PyYAML；Windows/macOS/Linux CI |
| 前端开发 | Node 20+；看工作台无需 Node |
| 真实浏览器观察 | macOS、Ego Lite 与 ego-browser Skill；自己的平台登录 |
| 实验性生成适配器 | 上述依赖 + Codex CLI、CLI 支持的模型与账号；需逐次授权 |

[Ego 官方网站](https://lite.ego.app/) 当前提供 Mac 下载，onboarding 安装 ego-browser Skill 和 CLI；未提供本项目可验证的 Windows/Linux 浏览器后端。不要把 Python CI 通过当作这些平台上的视频生成可用。

Codex 安装和登录按 [官方 CLI 文档](https://developers.openai.com/codex/cli) 操作。`doctor --browser` 检查 CLI、必要 exec 参数、登录状态、Ego 连接与 Skill 文件；这些检查通过仍不能证明模型账号有权限或 RunningHub 已登录。

```bash
python3 queue/automation.py doctor --browser
```

Codex 桌面模型别名可能不在 CLI 中可用。进入 `codex` 后用 `/model` 查看**自己账号的 CLI 模型**，退出后把该 ID 传给 `--agent-model`。可选执行一个真实模型调用（消耗当前 Codex 额度）：

```bash
# 把 CLI_MODEL 替换为上一步实际可用的 ID，再运行：
python3 queue/automation.py probe-agent --agent-model CLI_MODEL
```

执行器使用 workspace-write 沙箱并开启命令网络连接以访问 Ego；不使用全权限绕过参数，不改变全局 Codex 配置。网络设置依据 [官方配置契约](https://developers.openai.com/codex/config-reference)。宿主管理策略、hooks 或网络限制仍可能阻止执行，此时保留日志并处理宿主原因。

## 任务契约

`queue/anytime.yaml` 和 `points-21.yaml` 是原来的制作任务台账，允许文字依赖；不会被当成可执行命令。可执行任务只从 `queue/automation.yaml` 读取，避免把旧记录或任意 shell 文本误执行。

```yaml
version: 1
jobs:
  - id: my-render
    project: projects/my-story
    action: render
    depends_on: []
    enabled: true
  - id: my-ready
    project: projects/my-story
    action: check_ready
    depends_on: [my-render]
    enabled: true
```

先用脚手架创建 `my-story`，填写三个 YAML 记录后再加入此配置。ID 必须唯一；依赖只能填写同一文件内的 job ID，未知依赖或循环会在任何执行前报错。运行时按依赖排序，失败任务不放行后续任务。

| action | 实际效果 |
|---|---|
| render | 校验 YAML，原子替换各 Markdown 阅读页，刷新工作台 |
| check_ready | 检查当前引用文件、上传登记、完整摄影调度、参数及引用覆盖；不执行上传 |
| inspect_runninghub | 启动/复用该作品的 Ego 空间，打开指定页面，保存真实页面观察；不点击生成 |
| generate_runninghub | 实验适配器：调用 Codex 和 Skill 操作原画布；生成成功须带节点、可播放声明、截图与审片登记 |

默认例子只有 render 启用。教学 SVG 是草稿，check_ready 的预期结果是失败；不能为了通过检查随意标成 uploaded。登记上传依然需要代理在当前画布现场核对。

```bash
python3 queue/automation.py run                 # 计划，无写入
python3 queue/automation.py run --execute       # 实际执行准备/观察任务
python3 queue/automation.py run --job my-render --execute
python3 queue/automation.py status
python3 queue/automation.py watch --execute --interval 30
```

watch 每 30 秒重读配置和输入，实际执行就绪任务；输出仅在状态变化时出现。它不是后台服务、cron 或设备唤醒器。积分任务不会批量运行，也不允许以 point-budget 开启 watch。

## 真实 RunningHub 观察

在自己的 `project.yaml` 写入**既有画布的完整 HTTPS 链接**，然后加入任务：

```yaml
  - id: my-browser
    project: projects/my-story
    action: inspect_runninghub
    depends_on: [my-render]
    enabled: true
```

执行 `python3 queue/automation.py run --job my-browser --execute`。没有 canvas_url 时只能观察 RunningHub 首页，不能拿首页绑定执行生成。第一次建立空间后立即保存 spaceId/page；后续恢复仍用同一个空间，不绕过用户接管。

观察成功只表示真实页面已打开并有 snapshot；登录、模型、报价和已上传引用还需实际检查。观察本身不提交任务、不导入 Cookie，也不读取账号密钥。

## 实验性生成入口

先完成本地 ready 检查与原画布观察；配置中加入明确镜号：

```yaml
  - id: my-generate-01
    project: projects/my-story
    action: generate_runninghub
    shots: [1]
    depends_on: [my-ready, my-browser]
    enabled: true
```

`queue/index.yaml` 的执行策略默认关闭、预算为0。准备使用时，确认自己的授权范围，设置 `allow_existing_runninghub_points_at_21_00: true`、整数 `point_budget_per_run` 上限，并保持 `may_spend_rmb_wallet_or_purchase_topups: false`。

积分窗口由 `timezone`、`credit_queue_check_start`、`credit_queue_check_end` 决定，格式 HH:MM，起点包含、终点不包含；可以跨午夜，默认 21:00–22:00。窗口不是平台优惠保证，现价必须逐节点检查。

```bash
# 仅示范参数：CLI_MODEL 必须换成自己的有效模型 ID；50 是本次总授权上限。
python3 queue/automation.py run --job my-generate-01 --execute --point-budget 50 --agent-model CLI_MODEL
```

CLI 参数给出当前使用者对**这一项任务**的积分授权，不能超过配置上限；不持久化付款授权。过期或新一次恢复需要新的明确授权。单次最多授权一个生成任务，不能通过 watch 把旧授权无限延续。当前适配器不支持无人值守的积分定时提交或仅零费用的生成授权。

Python 能检查本地预算/窗口与结果契约，无法替平台拦截每一个浏览器扣费动作；现场费用和累积余额由代理检查。首次使用应在旁观察，直到自己的账号/流程完成验收。Codex 模型调用使用自己的 Codex 额度/API计费，与 RunningHub 积分分开。

每次生成保存独立运行目录；只有全部指定镜头都有原节点身份、可播放结果截图，并已登记 generated/review/passed 时，执行器才收为 done。**job 的 done 是该生成动作完成，不是整部作品已剪辑完成或审片通过。** JSON 或截图只能存档现场证据，不能自动证明审美质量，也不能用进程 exit 0 代替生成结果。

## 状态与恢复

运行状态、锁、浏览器绑定、截图和代理日志放在 `.private/automation/`，默认 Git 忽略且本地 HTTP 禁止读取。状态文件是执行事实来源，不会改写制作队列的文字记录。

- done：同输入已完成，重复运行跳过。本地准备输入变化后会重跑。
- failed：本地校验/准备失败，先改记录，再显式恢复。
- running：进程仍在运行，或硬中断留下的写前状态；不可直接重试。
- uncertain：浏览器/代理中断或结果不完整，可能已有现场效果。先查原节点与任务身份。
- waiting_browser / waiting_balance：需原空间登录/恢复控制，或核实余额。
- changed：已完成浏览器任务的输入变化，需要重新检查；不自动再提交。

```bash
python3 queue/automation.py status
# 确认进程已结束，且已查看原画布的任务/结果后：
python3 queue/automation.py recover --job my-generate-01 --acknowledge-after-inspection
```

恢复保存旧状态到历史，不删除浏览器绑定或成功镜头。它不是新费用授权。用户接管、登录或 CAPTCHA 后，由用户明确要求代理恢复原 spaceId；命令不会自动 claim 用户拥有的空间。执行中止时保留原绑定；不得新开空间绕过控制权。

电脑/进程崩溃留下 runner.lock 时，先确认 owner 进程不再存在，执行 `python3 queue/automation.py recover-lock`。若检测到同主机活进程，或无法验证，会拒绝删除锁。不同主机或损坏锁需人工检查，不能盲删。解锁不会改变 running/uncertain 状态，仍须检查后 recover。

更换画布时，先检查原空间并停止旧任务，记录旧绑定；同一个作品应继续使用原画布。确实换作品时建立新项目，不复用旧项目身份。对已有项目确需换链接的情况，本版不提供自动重绑，需代理在原空间处理并审计后更新绑定。
