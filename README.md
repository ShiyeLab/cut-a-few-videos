# 剪几个视频

把素材交给 Agent，做成带标题、字幕、配音和音乐的竖屏视频。Agent 负责理解要求、盘点素材、作出制作选择、调用工具和检查成片，Python 与 FFmpeg 负责排版和合成。

Fork 或下载项目后，在 Codex、Claude Code、DSH 等能读写文件、执行命令和查看媒体的 Agent 宿主中打开即可开始。默认推荐的主 Agent 是 **DeepSeek V4.1 Flash**，也可使用宿主支持的其他模型；模型在宿主中选择，仓库不绑定主模型 API。

## 开始制作

**1. 取得项目。** Fork 后下载 ZIP，或把下方 `YOUR_NAME` 换成自己的 GitHub 用户名：

```sh
git clone https://github.com/YOUR_NAME/cut-a-few-videos.git
cd cut-a-few-videos
```

**2. 放入素材。** 把文案、图片、视频、录音等放进 `projects/my-video/source/`。材料不必齐全，也不必先手填配置；Agent 会先检查已有内容，再判断缺什么。

**3. 交给 Agent。** 在宿主中打开仓库，发送：

> 请阅读 README.md、AGENTS.md 和 methods/制作流程.md。用 projects/my-video/source/ 中的材料，制作一条【主题、用途、期望时长】的竖屏视频。先盘点素材，查看实际画面和声音，判断已有口播与配音能否复用、画面是否足够、要不要补环境镜头、是否适合配公版音乐，以及贴片怎样设计。按我已说明的要求决定，只集中询问影响制作的缺项与偏好。在约定的生成预算内完成文案、选声、素材准备、无字贴片生图、字幕与镜头时序、合成和检查。使用默认推荐服务，或我指定的其他 Agent/API。输出到 projects/my-video/v1，交付可播放 MP4、配置和检查结果。

首次使用时，Agent 按[使用说明](docs/getting-started.md)检查 Python 3.12、FFmpeg 与 Pillow，协助准备中文字体和所需服务配置。已有声音和画面直接复用，只补实际缺少的内容。

## 制作流程

1. **看材料**：清点文件、查看图片与视频、听已有录音，记录可用片段和内容依据。
2. **定做法**：确定文案、声音、画面缺口、音乐、贴片风格、时长与生成预算。
3. **补齐输入**：需要时配音、检索素材或生成环境空镜；生成无字贴片底图。
4. **按声音排时间**：从真实音频取得字幕时间轴，再安排镜头、叠化与完整片尾。
5. **合成并检查**：生成 1080×1920 MP4，看画面、听声音、核对字幕与时长，修改后另存版本。

完整步骤与各阶段的判断依据见[制作流程](methods/制作流程.md)。

## 默认推荐，可逐环节替换

| 环节 | 默认推荐 | 换用其他工具时交给下一步的内容 |
| --- | --- | --- |
| 主 Agent | DeepSeek V4.1 Flash | 文案、制作判断、配置与工具执行 |
| 贴片生图 | Seedream 5.0 Pro | 本地无字海报 PNG/JPG |
| 环境视频 | MiniMax H3 | 本地视频片段与实际选段 |
| 配音 | 豆包语音合成 2.0 | 完整音频与匹配的真实字幕时间轴 |
| 补充素材 | 用户素材优先，按需检索 | 本地文件、来源与使用区间 |
| 音乐 | 按内容选择公版录音、用户提供的音乐或不配乐 | 本地音乐文件或空值 |

每个环节可独立更换。例如生图用另一家 API，配音继续用豆包；也可以全部使用自己的服务。Agent 调用所选 API，把结果保存为约定的文件格式后继续制作。具体字段与更换步骤见[服务选择与替换](docs/optional-services.md)。

**贴片默认先用生图 API 做底图**，从同一幅海报取上下两端，标题与底部文字由程序另排。每条视频重新选择色彩和画面风格，改标题无需重新生图。

## 先跑一个离线例子

安装环境后，从仓库根目录执行：

```sh
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/v1
```

得到 `projects/demo/v1/video.mp4`：8 秒、1080×1920、30 fps，包含图片推近、视频、中央叠化、贴片、字幕和合成音。输入由程序生成，不需要 Key。教学例的几何底图用于离线演示；自己的视频按上面的生图流程准备贴片。

## 文档

| 文档 | 用途 |
| --- | --- |
| [使用说明](docs/getting-started.md) | 环境、字体、配置与输入准备 |
| [制作流程](methods/制作流程.md) | Agent 如何盘点、判断、执行和检查 |
| [服务选择与替换](docs/optional-services.md) | 默认 API、调用命令与替换格式 |
| [工程说明](docs/工程说明.md) | 配置、文件关系、时序、合成和修改 |
| [单条视频模板](templates/video/) | 素材清单、要求、镜头、来源和配置 |
| [离线教学例](examples/demo/README.md) | 无需外部素材的完整运行例子 |
| [检查与交付](docs/validation.md) | 自动检查与实际看片 |
| [AI 执行说明](AGENTS.md) | 给制作 Agent 的工作要求 |
| [第三方依赖](THIRD_PARTY.md) | 字体、Pillow 与 FFmpeg |

自己的素材、声音、字体、回执与成片放在 `projects/`、`local/`，默认不进入 Git。维护者：[ShiyeLab](https://github.com/ShiyeLab)。
