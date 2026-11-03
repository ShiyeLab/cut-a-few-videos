# 安装和第一条视频

可以先把素材交给 Agent，再由 Agent 按本文检查环境并准备文件。使用者无需预先填写镜头表或技术参数。

## 首次运行由 Agent 完成

用户 clone 项目后不需要自己装任何东西。Agent 首次运行时在 macOS 上执行以下步骤，已存在的项跳过；需要输入系统密码或网络失败时再请用户处理。

```sh
# 1. 命令行依赖（未装 Homebrew 时先按 https://brew.sh 安装）
brew install python@3.12 ffmpeg node

# 2. Python 环境
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 3. MediaKit CLI（视频理解）
npx @volcengine/mediakit-cli install -y

# 4. 中文字体：思源宋体 Heavy，按 SIL OFL 1.1 使用
mkdir -p local/fonts
curl -fL -o local/fonts/SourceHanSerifSC-Heavy.otf \
  https://github.com/adobe-fonts/source-han-serif/raw/release/OTF/SimplifiedChinese/SourceHanSerifSC-Heavy.otf

# 5. 服务配置：只有这一步需要用户提供 Key
cp -n .env.example .env.local
python tools/check_credentials.py
```

装完后运行下一节的离线示例，确认合成链路可用。FFmpeg 需含 `libx264`、AAC、QTRLE 编码和 `overlay`、`xfade`、`perspective`、`loudnorm` 等滤镜，Homebrew 版本已包含。文字由 Pillow 渲染，不依赖 `drawtext` 或 `subtitles`。

Linux 按系统包管理器安装 Python 3.12 与 FFmpeg，然后执行相同的虚拟环境与依赖命令。Windows 准备 Python 3.12 和 FFmpeg，将 FFmpeg 的 `bin` 目录加入 PATH；在 PowerShell 用 `py -3.12 -m venv .venv` 建环境，后续把 `python` 换成 `.venv\Scripts\python.exe` 即可。

## 先跑离线示例

从仓库根目录执行：

```sh
python tools/test_video_fixes.py
python -m unittest discover -s tests -v
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/v1
```

输出 `projects/demo/v1/video.mp4`。它有合成和弦，没有人声，字幕是明确手工设定的教学时间轴。使用英文字体是为了在没有字体包时也能独立运行。

做一份全静音对照：

```sh
python tools/build_video.py --project examples/demo/project.json --work projects/demo/silent-v1 --no-music
```

示例输入可以重复生成；成片目录必须使用新名字。生成物都在忽略目录内。

## 中文字体

通用布局预设路径是 `local/fonts/SourceHanSerifSC-Heavy.otf`，首次运行时由 Agent 从 [Adobe 思源宋体官方发布](https://github.com/adobe-fonts/source-han-serif/tree/release/OTF/SimplifiedChinese)下载。仓库不分发字体包。换用其他 TTF 或 OTF 时放到 `local/fonts/`，修改布局中 `fonts.title.path`、`fonts.quote.path`、`fonts.subtitle.path`。保留官方 [OFL 许可](https://github.com/adobe-fonts/source-han-serif/blob/release/LICENSE.txt)。`pillow-default` 仅供英文离线教学例使用，不支持中文。

## Agent 准备制作输入

实际视频素材先按[MediaKit 视频理解](video-understanding.md)安装 CLI、填写 `MEDIAKIT_API_KEY`，由 Agent 提交分析并保存结果。离线教学例不调用服务。主 Agent 使用文字分析进行策划和编排，无需自身具备视频视觉能力。

```sh
mkdir -p projects/my-video
cp templates/video/* projects/my-video/
cp template/layout.json projects/my-video/layout.json
```

Agent 按[制作流程](../methods/制作流程.md)盘点用户材料，先取得完成的视频分析，再填写 `inventory.md`、`brief.md` 与纯口播 `script.txt`，明确是否配音、配乐和补画面。把真实素材放到 `projects/my-video/assets/`，在 `sources.json` 里记录本地文件、来源、用途、理解结果路径与选段依据。把音频及与它匹配的真实时间轴放到 `projects/my-video/voice-v1/`。默认 API 与替换方法见[服务选择与替换](optional-services.md)；使用自己录音时，根据实际录音制作相同格式的时间轴。

Agent 用生图 API 生成无字海报，或复用用户提供的合适底图；使用 `band_art` 导入，上下取同一幅图，文字另排。

编辑 `project.json`：填写标题、布局、口播、声音、时间轴、镜头表、配乐和贴片底图路径。所有路径都相对仓库根目录，包含空格时命令参数加引号。`scenes.json` 的每个镜头用口播句首定位；源起点按实际素材的可用区间填写。

```sh
python tools/build_video.py --project projects/my-video/project.json --work projects/my-video/v1
```

看完后只改有问题的部分，再输出 `v2`。更换口播或声音要重做时间轴；只换画面可以复用声音。文件关系与参数见[工程说明](工程说明.md)。
