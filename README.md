# 剪几个视频

把素材交给 Agent，做成带标题、字幕和配音的抖音推书竖屏视频，可一次出 1 条或若干条彼此不同的成片；配乐由用户最后在剪映添加。MediaKit 负责视频内容理解，主 Agent 读取分析、设计内容并编排镜头，Python 与 FFmpeg 负责排版和合成。

Fork 或下载项目后，在 Codex、Claude Code、DSH 等能读写文件、执行命令的 Agent 宿主中打开即可开始。默认推荐的主 Agent 是 **DeepSeek V4.1 Flash**，也可使用宿主支持的其他模型；模型在宿主中选择，仓库不绑定主模型 API。视频视觉分析通过 MediaKit 调用完成，不要求主模型自行看懂视频。

## 开始制作

**1. 取得项目。** Fork 后下载 ZIP，或把下方 `YOUR_NAME` 换成自己的 GitHub 用户名：

```sh
git clone https://github.com/YOUR_NAME/cut-a-few-videos.git
cd cut-a-few-videos
```

**2. 放入素材。** 把文案、图片、视频、录音等放进 `projects/my-video/source/`。材料不必齐全，也不必先手填配置；Agent 会先检查已有内容，再判断缺什么。

**3. 交给 Agent。** 在宿主中打开仓库，发送：

> 请阅读 README.md、AGENTS.md 和 methods/制作流程.md。用 projects/my-video/source/ 中的材料，制作【条数】条【主题、期望时长】的抖音推书竖屏视频，面向【目标观众】，让观众理解或感受到【主要内容】。先盘点素材，调用 MediaKit 取得视频理解，核对图片与声音，再确定表达、选声和镜头安排。采用片段前确认实际画面能承担该段作用，按需要补素材，不为凑镜头数或转场种类制作。保留我的定稿与已明确要求，只集中询问影响制作的缺项、偏好和费用。在约定预算内用默认推荐服务或我指定的 Agent/API 完成制作，核对完整成片的声画关系、节奏、字幕与片尾。输出到 projects/my-video/out/，交付同一版本的 MP4、配置、来源和检查结果。

首次使用时，Agent 按[使用说明](docs/getting-started.md)自动安装 FFmpeg、Python 环境、MediaKit CLI 并下载中文字体，用户只需提供服务 Key。已有声音、画面和有效分析直接复用，只补实际缺少的内容。

## 制作流程

1. **理解材料**：清点文件，调用 MediaKit 分析视频；核对图片、录音的内容依据，记录可用片段与不确定项。
2. **定表达**：明确内容怎样推进、画面与声音各自承担什么，再决定缺口、风格与预算。
3. **确定声音和时序**：试听选声，从完整音频取得真实字幕时间轴，安排关键节点与片尾。
4. **选镜与补画面**：按实际作用采用素材，需要时检索或生成；检查结果后决定保留、调整或弃用。
5. **合成并检查**：生成 1080×1920 MP4，核对观看是否连贯、声画是否对应，再查文字和技术完整性，修改后另存版本。

完整步骤与各阶段的判断依据见[制作流程](methods/制作流程.md)。镜头数量、静帧比例、复用次数和转场种类仅帮助发现问题；实际表达、用户要求与预算决定采用方式。

## 默认推荐，可逐环节替换

| 环节 | 默认推荐 | 换用其他工具时交给下一步的内容 |
| --- | --- | --- |
| 主 Agent | DeepSeek V4.1 Flash | 文案、制作判断、配置与工具执行 |
| 视频理解 | MediaKit `video-understand-router` | 逐文件内容分析、候选源区间、选用理由与不确定项 |
| 贴片生图 | Seedream 5.0 Pro | 本地无字海报 PNG/JPG |
| 补充镜头视频 | MiniMax H3 | 本地视频片段与实际选段 |
| 配音 | 豆包语音合成 2.0 流式语气方案 | 完整音频与匹配的真实字幕时间轴 |
| 补充素材 | 用户素材优先，按需检索 | 本地文件、来源与使用区间 |

每个环节可独立更换。例如生图用另一家 API，配音继续用豆包；也可以全部使用自己的服务。Agent 调用所选 API，把结果保存为约定的文件格式后继续制作。具体字段与更换步骤见[服务选择与替换](docs/optional-services.md)。

**贴片默认用生图 API 做底图**，已有合适无字底图可复用。从同一幅海报取上下两端，去掉白卡片，标题与底部文字由程序另排，使用细描边与轻微深色投影。风格随内容确定，改标题无需重新生图。

## 先跑一个离线例子

安装环境后，从仓库根目录执行：

```sh
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/v1
```

得到 `projects/demo/v1/video.mp4`：8 秒、1080×1920、30 fps，包含匀速推近与平移、视频选段、推入与闪白转场、贴片、字幕和合成音。输入由程序生成，不需要 Key。教学例的几何底图用于离线演示；自己的视频按上面的生图流程准备贴片。

## 导出可编辑剪映草稿

在装有剪映的 Mac 或 Windows 上运行 `build_video.py`，合成后会自动在剪映草稿目录生成这条视频的草稿，打开剪映即可在首页看到：中央窗画面、底图、标题、底部文字、字幕和配音各自成轨，文字可以直接改，素材可以换。草稿和 MP4 用同一份时间轴；镜头之间是硬切，不带运镜与转场，过场、配乐和字体在剪映里自己加。

合成时剪映正开着，草稿照常生成，只是暂不登记首页；退出剪映后运行 `python tools/jianying_draft.py --register` 补上。不需要草稿时给 `build_video.py` 加 `--no-jianying`；给以前的输出目录补导出用 `python tools/jianying_draft.py --work <输出目录>`。

首次使用可先运行 `python tools/jianying_smoke.py` 生成一份 6 秒测试草稿，确认本机剪映能打开。首页登记、仅生成文件的用法与验收步骤见[验证说明](docs/validation.md#剪映草稿)。

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
| [开源依赖与署名](THIRD_PARTY.md) | 实际使用的项目、用途、代码入口与许可证 |

## 开源致谢

本项目使用 [FFmpeg](https://ffmpeg.org/) 处理音视频、[Pillow](https://github.com/python-pillow/Pillow) 绘制文字与图片、[MediaKit CLI](https://github.com/volcengine/mediakit-cli) 接入视频理解、[pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) 生成可编辑剪映草稿。感谢各项目作者与贡献者；实际调用入口和许可证见[署名说明](THIRD_PARTY.md)。

自己的素材、声音、字体、回执与成片放在 `projects/`、`local/`，默认不进入 Git。维护者：[ShiyeLab](https://github.com/ShiyeLab)。
