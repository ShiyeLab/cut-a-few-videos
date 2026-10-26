# 安装和第一条视频

## 准备环境

Python 使用 3.12。FFmpeg、ffprobe 需在终端可执行，FFmpeg 需含 `libx264`、AAC、QTRLE 编码和 `overlay`、`xfade`、`zoompan`、`loudnorm` 等滤镜。文字由 Pillow 渲染，不依赖 `drawtext` 或 `subtitles`。

macOS 可用 Homebrew 安装：

```sh
brew install python@3.12 ffmpeg
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Linux 按系统包管理器安装 Python 3.12 与 FFmpeg，然后执行相同的虚拟环境与依赖命令。Windows 准备 Python 3.12 和 FFmpeg，将 FFmpeg 的 `bin` 目录加入 PATH；在 PowerShell 用 `py -3.12 -m venv .venv` 建环境，后续把 `python` 换成 `.venv\Scripts\python.exe` 即可。当前实际验证环境为 macOS。

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

中文标题与字幕需要支持相应文字的 TTF 或 OTF。把自己的字体放到 `local/fonts/`，修改布局中 `fonts.title.path`、`fonts.quote.path`、`fonts.subtitle.path`。仓库不分发字体包。

通用布局预设路径是 `local/fonts/SourceHanSerifSC-Heavy.otf`，可从 [Adobe 思源宋体官方发布](https://github.com/adobe-fonts/source-han-serif/tree/release/OTF/SimplifiedChinese)取得该字体。保留官方 [OFL 许可](https://github.com/adobe-fonts/source-han-serif/blob/release/LICENSE.txt)。`pillow-default` 仅供英文离线教学例使用，不支持中文。

## 准备自己的输入

```sh
mkdir -p projects/my-video
cp templates/video/* projects/my-video/
cp template/layout.json projects/my-video/layout.json
```

填写 `brief.md` 和纯口播 `script.txt`。把真实素材放到 `projects/my-video/assets/`，在 `sources.json` 里记录本地文件、来源、用途与已看过的片段。把音频及与它匹配的真实时间轴放到 `projects/my-video/voice-v1/`。配音工具的命令见[可选服务](optional-services.md)；使用自己录音时，根据实际录音制作相同格式的时间轴。

编辑 `project.json`：填写标题、布局、口播、声音、时间轴、镜头表、配乐和贴片底图路径。所有路径都相对仓库根目录，包含空格时命令参数加引号。`scenes.json` 的每个镜头用口播句首定位；从实际素材中选择源起点，不沿用其他书的秒数。

```sh
python tools/build_video.py --project projects/my-video/project.json --work projects/my-video/v1
```

看完后只改有问题的部分，再输出 `v2`。更换口播或声音要重做时间轴；只换画面可以复用声音。文件关系与参数见[工程说明](工程说明.md)。
