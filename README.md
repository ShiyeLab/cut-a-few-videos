# 剪几个视频

把口播稿、图片和实拍片段做成带标题、字幕、配音与音乐的竖屏视频。AI 负责读材料、理解文案、选声选镜和检查效果，Python 与 FFmpeg 负责排版、时序和合成。

项目整理自两条推书视频的制作实践，提供方法、配置模板、本地工具和离线教学例。适合让能读写文件、运行命令和查看媒体的编程代理协助制作一条视频，再按观看反馈修改。

## 可以做什么

- **按口播配画面**：用实际字幕时间定位镜头起点，完整保留末句和片尾。
- **设计上下贴片**：从同一张无字底图取上下两端，标题与底部文字由程序排版；每条视频自行选色。
- **处理图片与过场**：居中缓慢推近、完整展示或裁切填满，中央画面之间做叠化。
- **独立处理声音**：人声加音乐、只有人声、只有音乐、全静音，素材视频的原声不混入。
- **检查结果**：文字超框、字幕时序、镜头源区间、音视频时长与完整解码；生成后继续看片、听声音。

豆包配音、MiniMax 环境空镜和 Pexels 候选检索是可选工具。已有素材与声音时，合成全部在本地完成。文案、镜头与声音选择由使用者和代理决定。

## 快速开始

需要 Python 3.12、FFmpeg 与 ffprobe。以下命令在仓库根目录执行。

```sh
git clone https://github.com/ShiyeLab/cut-a-few-videos.git
cd cut-a-few-videos
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/v1
```

打开 `projects/demo/v1/video.mp4`：8 秒、1080×1920、30 fps，包含图片推近、视频片段、中央叠化、上下贴片、字幕和合成音。检查结果在同目录的 `verify.json`。

示例由程序生成几何图形、测试视频和和弦，使用 Pillow 自带的英文字体；无需下载素材、填写 Key 或调用模型。再次制作请换成 `projects/demo/v2`，保留旧版。环境安装与静音示例见[使用说明](docs/getting-started.md)，示例输入见[教学例](examples/demo/README.md)。

## 做自己的视频

把资料放进 `projects/my-video/`，参考[单条视频模板](templates/video/)准备口播、声音、时间轴与镜头表。中文制作另行准备中文字体，方法见[使用说明](docs/getting-started.md#中文字体)。

可以直接把下面的指令交给 AI：

> 请先读 AGENTS.md、docs/工程说明.md 和 methods/制作流程.md。我要做一条【主题或书名】的视频，资料在 projects/my-video/，要求在 brief.md。本次只做【明确范围】，保留已有版本。先核对资料，把口播意思落实成可见的动作和场景；展示产品时使用这个产品的真实素材。按内容选配音、配色和无字贴片底图。已有声音先复用，只有获得本次授权后才调用付费服务。按真实声音时间安排字幕与镜头，完整保留末句和片尾。用新目录输出可播放视频，检查画面、声音、字幕与时长，并说明实际缺少的材料。

`projects/`、`local/` 和示例生成物默认不进入 Git。仓库不附带原书资料、照片、影片、配音、音乐、字体包或服务回执。

## 文档

| 文档 | 用途 |
| --- | --- |
| [使用说明](docs/getting-started.md) | 安装、运行示例、准备自己的输入 |
| [工程说明](docs/工程说明.md) | 流程、配置、文件关系、参数、修改与恢复 |
| [制作流程](methods/制作流程.md) | 从口播到选声、选镜、贴片和看片检查 |
| [可选服务](docs/optional-services.md) | 配音、空镜、候选素材与回执处理 |
| [配置与提示词模板](templates/) | 单条任务、选材、配音演绎、海报与空镜 |
| [两本书的制作方法](examples/cases/README.md) | 不同内容如何影响声音、色彩和画面 |
| [验证说明](docs/validation.md) | 离线测试与交付检查 |
| [来源说明](THIRD_PARTY.md) | 代码、教学例、字体与参考项目 |
| [AI 执行约定](AGENTS.md) | 给接手代理的工作规则 |

维护者：[ShiyeLab](https://github.com/ShiyeLab)。
