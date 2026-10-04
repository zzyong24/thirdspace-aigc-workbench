# Thirdspace AIGC Workbench

- Each work lives in `projects/<slug>/`. Create it with `python3 projects/new_project.py <slug> --title <title>` and follow `projects/AGENTS.md`.
- Versioned YAML records own asset, shot and audit data. Run `python3 projects/render_records.py projects/<slug>` to validate and update Markdown reading views, then `python3 queue/build_board.py`.
- The dashboard is a read-only snapshot. Edit project records and queue YAML first; never change the embedded JSON by hand.
- UI source is `queue/board-ui/`; use Ant Design 6 documented APIs, query local `antd info` before component changes, lint with `antd lint --format json`, and run `npm run build` before rebuilding the board.
- Keep one browser workspace and one RunningHub canvas per work. Follow `.agents/skills/runninghub-minimax-story-video/SKILL.md` and the separately installed `ego-browser` Skill.
- New installations have no points authorization or scheduler. A configuration flag is not evidence of user payment authorization. Confirm authorization in the current user context and inspect live cost before submission. Never charge cash or top up credits.
- Do not commit credentials, browser state, private canvas URLs, personal reference images, private projects or logs. Keep example projects explicitly marked as examples.
- Preserve existing user edits, completed tasks, rejected versions and audit evidence. Recover the original job before retrying; an export is complete only after its actual result plays.
- Executable jobs live in queue/automation.yaml, separate from legacy human planning queues. Run queue/automation.py without --execute to inspect first. Never translate arbitrary task text into a shell command.
- RunningHub generation adapter is experimental pending real end-to-end acceptance. Do not upgrade its status in docs from unit tests, a CLI handshake or a browser observation alone.
