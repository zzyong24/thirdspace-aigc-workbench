# 项目制作规范

每个作品使用独立 `projects/<slug>/` 目录；根目录 `project.yaml` 记录作品名、阶段、画幅、时长与交付方式。创建：`python3 projects/new_project.py <slug> --title <title>`。

## 文件与记录

- `proposal.md`：创意、目标观众、规格和待确认项。
- `research.md`：事实来源、解读与创作选择分开。
- `script.md`：旁白、对白、声音和字幕设计。
- `project_assets.md`：素材来源、许可、缺项与交付物。
- `assets/asset-matrix.yaml`：版本为 1，登记人物、场景、道具、镜头覆盖、图像与上传状态。
- `prompts/shots.yaml`：版本为 1，逐镜动作、时长、参考资产、摄影调度和生成参数。
- `shot_audit.yaml`：版本为 1，逐镜提交/生成/审片状态；运行细节记入 `run-log.md`。
- `assets/audio/source.yaml`：音源文件、来源与授权状态。没有音源就记缺失，不能把流媒体链接当音频文件。

YAML 是结构化项目的唯一维护源。`assets/asset-matrix.md`、`prompts/shot-prompts.md`、`storyboard.md` 和 `shot_audit.md` 由 `python3 projects/render_records.py projects/<slug>` 生成；直接编辑生成页会在下次渲染时被覆盖。旧的仅 Markdown 项目仍可被工作台读取；新项目采用 YAML。

## 素材与摄影调度

人物、场景、道具分别存放在 `assets/characters/`、`assets/scenes/`、`assets/props/`；图像提示词在 `prompts/assets/`。生成前完成全部适用的正面、侧面、背面三视图，核验人物身份与空间布局。示例 SVG 为教学示意，真实任务需制作和检查完整参考图。

每镜写全 camera 的 `start`（起始景别、机位、轴线）、`move`（带时间段的方向、速度、幅度）、`stop`（停点、末帧构图、何时稳定）、`continuity`（出入画、视线轴、下一镜承接）。用实际场景三视图检查路径，生成后检查首/中/尾帧。技术校验不能替代画面审查。

## 运行与交付

每个作品一张 RunningHub 画布，一个 Ego Lite TaskSpace；参考图在左、编号镜头在右，卡片和连线清晰。节点提交前核对模型、模式、引用、参数、当前费用与余额；积分需当前用户明确授权，不因队列配置为 true 自动获得授权，不使用现金或充值。

提交前执行 `python3 projects/render_records.py projects/<slug> --check --ready`，再进行现场核验；本地校验通过不证明已上传、当前价格或生成质量。缺项时只暂停受影响任务并写明原因。

在线编辑核对来源、顺序、裁切、间隙、画幅和总长；画布出现可播放成品后才能标记完成。下载镜头放 `generated/shots/`，成片与工程放 `exports/`。运行记录改变后重建工作台。
