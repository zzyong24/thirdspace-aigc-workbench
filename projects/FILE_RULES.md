# 文件、版本与结构化记录

项目 ID 使用英文小写、数字和连字符，并和目录名一致。人物为 C01、场景为 S01、道具为 P01；同一身份/场景/物件保留 ID，内容改变保留旧文件并递增 `v01`、`v02`。资产矩阵只登记该 ID 当前版本；历史文件与采用依据保存在项目目录和日志中。

| 内容 | 位置与命名 |
|---|---|
| 人物图 | `assets/characters/C01-robot-turnaround-v01.png` |
| 场景图 | `assets/scenes/S01-rooftop-turnaround-v01.png` |
| 道具图 | `assets/props/P01-light-turnaround-v01.png` |
| 资产图提示词 | `prompts/assets/C01-robot.md` |
| 视频提示词维护源 | `prompts/shots.yaml` |
| 镜头视频 | `generated/shots/shot-01-rooftop-v01.mp4` |
| 音源及许可 | `assets/audio/` 与 `source.yaml` |
| 成片/工程 | `exports/<slug>-master-v01.mp4` |

资产矩阵的 image 相对 `assets/`；prompt_file 和审片记录的 video 相对项目根目录。绝对路径和越出项目的路径会被校验器拒绝。示例提供 SVG，真实图像可使用 PNG/JPEG/WebP 等浏览器支持格式。

结构示例见 `projects/demo-rooftop/`，详细字段见 `docs/records.md`。三个 YAML 文件使用 `version: 1`；唯一镜号使用正整数，重复 ID、未知参考资产、未知镜头、非正数时长或不支持的版本会导致构建失败，避免悄悄生成错误看板。

代码、文档和示例小图使用普通 Git。本仓库没有强制 Git LFS；自己的大图片、音视频可按需安装 LFS 并配置 `.gitattributes`。不要公开私人项目和运行日志。工作台不下载 RunningHub 视频。
