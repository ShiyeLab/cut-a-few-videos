# 可选的配音、空镜与素材工具

已有本地素材、声音和时间轴就能合成，不需要配置服务。使用在线工具时，复制 `.env.example` 为 `.env.local`，只填写要用的服务。所有工具只读指定文件，不自动读取 shell、其他项目或个人配置。

```sh
cp .env.example .env.local
python tools/check_credentials.py
```

检查只显示变量名与 PRESENT/ABSENT，不联网。`--env` 可明确指定另一个配置文件。配置格式是 `NAME=value`，不是需要执行的 shell 脚本。

## 豆包配音

使用 `VOLCENGINE_TTS_API_KEY`。工具配置为豆包语音合成 2.0、资源 `seed-tts-2.0`，音色由 `--speaker` 选择；例子中的音色只是已有候选，仍须根据内容试听。

短试听和完整流式配音的演绎要求保存在独立文件：

```sh
python tools/doubao_preview.py --script projects/my-video/preview.txt \
  --direction projects/my-video/direction.txt \
  --speaker zh_female_qingxinnvsheng_uranus_bigtts --rate 0 \
  --work projects/my-video/preview-v1

python tools/doubao_tts_stream.py --script projects/my-video/script.txt \
  --direction projects/my-video/direction.txt \
  --speaker zh_female_qingxinnvsheng_uranus_bigtts --rate 0 \
  --work projects/my-video/voice-v1
```

这些命令会实际发起配音。短试听工具限 300 字符，完整流式工具限 900 字符；更长稿件先按完整意思拆成独立制作段。流式接口为 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`，音频块在本地拼接，字级结果必须完整对应正文。

不需要演绎指令时，也可使用已有异步工具：

```sh
python tools/doubao_tts.py --script projects/my-video/script.txt \
  --speaker zh_male_shenyeboke_uranus_bigtts --rate 0 \
  --work projects/my-video/voice-async-v1
```

异步工具首次提交到 `/api/v3/tts/submit`，随后查询 `/query`。返回 running、退出码 3 表示还在处理，稍后用相同参数运行原命令，查询原任务，不提交新任务。

生成目录保留 `voice.mp3`、`timeline.json`、请求与回执。时间轴由字级时间整理，拒绝缺字或顺序不符；它不是按字数估算。`timeline.json` 用于排镜头，合成入口会另行生成显示略有延长的 `subs.json`。服务回执可能包含临时下载地址，只留在自己的项目目录。

### 中断和参数变化

- 完整成功后，同参数重跑复用已存在结果。
- 文案、音色、语速或演绎要求改变，使用新的配音目录。
- 异步请求响应丢失时保留提交前写下的任务号，后续只查询。
- 流式接口没有 task_id；断线、时间戳失败或未完成状态都不能续传。先检查回执与临时音频，确认需要重做后另建新目录，不删旧回执强行重试。
- `voice_stats.py 音频路径` 可统计停顿和音量，声音是否自然仍需听完整口播。

## MiniMax 环境空镜

使用 `MINIMAX_API_KEY`，工具站点为 `https://api.minimaxi.com`，模型配置为 `MiniMax-H3`。应使用与该站点匹配的配置。

复制并修改[空镜模板](../templates/ai-video.json)，用新的 `slug` 标识本次镜头。模板只描述无人、无手、无书、无文字的环境画面。

```sh
python tools/minimax_video.py --spec templates/ai-video.json --out projects/my-video/ai
python tools/minimax_video.py --spec templates/ai-video.json --out projects/my-video/ai --poll-only
```

第一条会提交新镜头；先提交全部尚未提交的项目，再查询各自任务。`--only window-light` 可只处理指定 slug，`--timeout` 控制一次轮询等待秒数，默认 900。查询中断只重查原任务，提交失败或未知结果不自动重提。

每个镜头目录保留提示词、回执、`clip.mp4` 与三张抽帧图。已有 downloaded 结果直接跳过；改变提示词时必须改 slug，不能用旧 slug 指望程序重新生成。超过等待时间后用同一目录和 `--poll-only` 继续查询。返回退出码 0 只表示这一轮处理结束，是否完成应看回执的 downloaded 状态与实际文件。

生成后逐条核对抽帧与连续画面，检查禁用内容、真实动作与所需片段时长，再写入镜头表。

## 贴片底图

制作实践使用 Seedream 生成无字竖版底图，标题由程序排。仓库提供[海报提示词](../templates/poster-prompt.txt)，不包含独立 Seedream 生图客户端。通过使用者已有且获准的生图工具生成后，把 PNG 或 JPG 存入本条素材目录，在 `project.json` 的 `band_art` 填写路径即可。

无字底图不是最终标题图。禁止把书名、宣传语或印章画进底图；这样修改标题时只重排文字，底图可以复用。当前离线教学例用程序绘制的几何底图演示相同的裁切与排字过程。

## Pexels 候选检索

使用 `PEXELS_API_KEY`，按[检索需求模板](../templates/stock-brief.json)填写可见动作与环境，再运行：

```sh
python tools/stock_search.py --brief templates/stock-brief.json \
  --per-shot 2 --out projects/my-video/stock
```

工具按竖屏筛选候选，下载 MP4，抽取 1 秒处图片，并记录来源页面、作者、素材编号和许可页。候选不会自动写入镜头表；还需完整检查片段、选区间和中央窗裁切。工具使用 [Pexels 视频 API](https://www.pexels.com/api/documentation/)，当前账号能否调用由自己的配置决定。

33 搜帧只有人工搜索与部分预览记录，仓库不包含下载或 API 集成。
