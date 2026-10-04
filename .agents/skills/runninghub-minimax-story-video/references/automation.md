# 执行与恢复

独立安装本 Skill 后，由宿主代理读 ego-browser Skill 并执行其真实 CLI；不是一个只凭 Skill 名称就会后台运行的服务。

浏览器依赖从 https://lite.ego.app/ 安装，完成 onboarding 后会安装 ego-browser Skill 和 CLI。当前官网提供 Mac 下载，Windows/Linux 不应声称浏览器生成支持。使用者自己登录 RunningHub；不要分发 Cookie 或绕过权限。

随完整工作台一起使用时，queue/automation.py 提供严格依赖、真实 render/check_ready/inspect_runninghub、持久化状态、锁和恢复。CLI参数和实例见仓库 docs/automation.md。单独安装 Skill 不会复制工作台执行器；不要在独立安装目录执行不存在的 queue 命令。

scripts/inspect_browser.mjs 是 Ego runtime 脚本，不可直接 node 执行。工作台执行器通过 stdin 注入 AIGC_BROWSER_REQUEST 对象（project/url/stateFile），由 ego-browser nodejs 运行；不依赖透传自定义环境变量。独立代理如复用此辅助脚本，先创建私有状态父目录，注入自己的绝对 stateFile、已有画布 HTTPS URL 和作品名，再提交脚本；保存的 spaceId/page 必须随作品保留。

console 输出可能在 stderr；解析输出时检查stdout和stderr两者。先保留日志并核对returncode，再读取结构化观察。snapshot只证明现场观察，不能证明账户已登录、费用为0或可提交。

生成适配器仍是实验状态，需要本次明确积分授权、可用的Codex CLI模型和原浏览器绑定；UI动作由代理按本Skill执行，尚未完成公开示例的端到端生成验收。不能向使用者承诺“安装即自动生成”或无人值守保证。

任何超时都先查原节点与任务身份，不换空间、不盲重试。交还用户的空间只能在用户明确恢复后继续。执行器recover记录恢复操作，保留原绑定与旧状态；它不构成新的费用授权。
