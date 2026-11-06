# 默认服务与替换方法

主 Agent 默认推荐 **DeepSeek V4.1 Flash**，在支持它的 Agent 宿主中选择；使用 Codex、Claude Code、DSH 等工具时，也可以直接用各自支持的模型。宿主需要能读写项目文件、执行命令。主模型负责策划和组织制作，视频内容分析默认交给 MediaKit，主模型读取其结果后编排；仓库里的脚本负责调用工具、处理与合成。

视频理解默认 MediaKit，生图默认 Seedream 5.0 Pro，补充镜头视频默认 MiniMax H3，配音默认豆包语音合成 2.0 流式语气方案。**每个环节都能独立更换**，已有素材和有效分析直接复用。所选服务、模型、分析批次与生成数量写入本条 `brief.md`。

## 更换服务后怎样继续

| 环节 | 交给合成步骤的文件 | 填写位置与检查 |
| --- | --- | --- |
| 视频理解 | 逐文件内容、候选源区间、选用理由、不确定项及原始分析 | 先写入 `inventory.md` 和 `sources.json`，再由主 Agent 编排 `scenes.json` |
| 生图 | 无字海报 PNG/JPG | `project.json` 的 `band_art`；检查上下裁切、留字区域和实际内容 |
| 生视频或视频检索 | 本地 MP4 等 FFmpeg 可读视频 | `scenes.json` 的 `asset`、`in`；检查真实动作、尺寸和源区间，给叠化留足尾段 |
| 配音或用户录音 | MP3/WAV/M4A 等完整音频 | `project.json` 的 `voice`；听完整口播，记录对应的实际时间轴 |
| 转写与对齐 | `timeline.json` 数组，每条有 `start`、`end`、`text` | `project.json` 的 `timeline`；时间单位为秒，正文完整且顺序一致，不能均分估时 |
| 音乐 | 默认不配乐，用户在剪映添加 | `project.json` 的 `music` 保持 null |
| 主 Agent | 文案、素材选择与项目配置 | 不改变以上文件约定；能执行本地工具即可 |

例如，换用其他生图 API 时，Agent 按该服务的协议调用，保存图片，再把 `band_art` 改成图片路径。配音服务不返回时间戳时，继续使用独立对齐工具或按实际音频标注，不需要改合成器。

专用脚本各自使用对应服务的协议；更换供应商通常需要按新协议调用，不能只换 URL 就认为完成适配。服务调用得到的文件只要符合上表，后续排版与合成可保持相同方式。

## 配置所需服务

使用随仓库提供的在线工具时，复制 `.env.example` 为 `.env.local`，只填写要用的服务。工具只读取指定配置文件，不自动读取 shell 或其他项目的配置。

```sh
cp .env.example .env.local
python tools/check_credentials.py
```

检查只显示变量名与 PRESENT/ABSENT，不联网。`--env` 可明确指定另一个配置文件。配置格式为 `NAME=value`。已有所需文件或只跑离线示例时，不需要 Key。

## MediaKit 视频理解

使用 `MEDIAKIT_API_KEY` 与官方 `mediakit-cli`，调用 `video-understand-router`，默认 `scene=editing`、`level=Quality`。完整安装、提交、任务恢复和镜头表衔接见[视频理解](video-understanding.md)。入口为 `tools/understand_video.py`；它保存真实任务号、查询结果和 `analysis.md`，供主 Agent 阅读。

视频理解是素材准备的一部分。缺少配置或分析失败时不能默认让文本主模型自行理解视频；先处理配置、查询原任务或使用用户指定的其他理解服务。已有同一素材和目标的有效分析可复用。

## Seedream 贴片生图

使用 `ARK_IMAGE_API_KEY`。默认模型为 `doubao-seedream-5-0-pro-260628`，接口为 `https://ark.cn-beijing.volces.com/api/v3/images/generations`，请求与返回格式见[火山方舟图片生成 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)。

Agent 参考[海报提示词](../templates/poster-prompt.txt)，按内容确定配色、质感和边缘元素，把具体提示词保存为 `projects/my-video/poster-prompt.txt`。生成一张无字竖版底图，标题与底部文字由程序排。

```sh
python tools/seedream_image.py --prompt projects/my-video/poster-prompt.txt \
  --work projects/my-video/poster-v1
```

这条命令会实际请求生图。默认尺寸为 1080×1920，`--size` 可调整尺寸；`--model` 可选同接口兼容的其他模型。加 `--dry-run` 只查看请求正文，不读取 Key、不联网。

结果保存为 `poster-v1/poster.png`，同时保存请求正文与状态回执。把该图片路径填入 `band_art`，由同一张海报裁出上下条带。底图不得带文字、印章、logo 或边框；修改标题只需重新排字。

同一工具也用来生成补充静帧：默认近方形中央窗可用 `2048x2048`，其他布局按实际显示区域选尺寸。每张用新的结果目录，图片作为镜头素材写入 `scenes.json`，按需要设置 `move`，省略则保持静止。

同参数且图片完整时复用结果；提示词或参数改变时使用新目录。请求中断、返回错误或图片无法读取时保留状态，不自动再次提交。Agent 检查回执后，在已授权范围内决定如何继续。

## 豆包配音

使用 `VOLCENGINE_TTS_API_KEY`。默认用 `doubao_tts_stream.py` 的单向流式语气方案，资源为 `seed-tts-2.0`；音色由必填的 `--speaker` 明确选择。示例音色应按内容替换和试听，字幕分条与换行不决定朗读停顿。

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

这些命令会实际发起配音。短试听工具限 300 字符，完整流式工具限 900 字符；更长稿件按完整意思拆成独立制作段。流式接口为 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`，音频块在本地拼接，字级结果必须完整对应正文。

不需要演绎指令时，也可使用异步工具：

```sh
python tools/doubao_tts.py --script projects/my-video/script.txt \
  --speaker zh_male_shenyeboke_uranus_bigtts --rate 0 \
  --work projects/my-video/voice-async-v1
```

异步工具首次提交到 `/api/v3/tts/submit`，随后查询 `/query`。返回 running、退出码 3 表示还在处理，稍后用相同参数运行原命令，查询原任务。

生成目录保留 `voice.mp3`、`timeline.json`、请求与回执。时间轴由字级时间整理，拒绝缺字或顺序不符。合成入口会另行生成显示略有延长的 `subs.json`。服务回执只保存在自己的项目目录。

完整成功后，同参数重跑复用结果。文案、音色、语速或演绎要求改变，使用新配音目录。异步响应丢失时保留提交前的任务号，后续只查询；流式接口没有可续传的 task_id，中断后先检查回执和临时音频，确定重做后另建目录。`voice_stats.py 音频路径` 可统计停顿和音量，声音是否自然仍需听完整口播。

## MiniMax 补充镜头视频

使用 `MINIMAX_API_KEY`，站点为 `https://api.minimaxi.com`，模型为 `MiniMax-H3`。配置须与该站点匹配。

需要生成视频时可使用 MiniMax；是否生成、生成多少以及怎样复用，由镜头作用、可用素材和已授权预算决定。可把本次需要的镜头集中写在一个规格文件里，默认 768P；不按镜头所处位置分配服务或规定固定条数。

Agent 复制[补充镜头模板](../templates/ai-video.json)，保存到本条目录，用新的 `slug` 标识每个镜头。模板只示范写法：第一条是故事人物镜头，第二条是点缀用的隐喻；按[制作流程](../methods/制作流程.md#4-选镜头与补画面)设计本条实际需要的画面。默认近方形中央窗用 `ratio: 1:1`，其他布局按实际窗口选择工具支持的比例。补充镜头默认无文字、无书；物件镜头不出现手，人物镜头按内容自然入镜，不能冒充真实人物、事件或产品使用证据。

```sh
python tools/minimax_video.py --spec projects/my-video/ai-video.json --out projects/my-video/ai
python tools/minimax_video.py --spec projects/my-video/ai-video.json --out projects/my-video/ai --poll-only
```

第一条会提交新镜头；先提交全部尚未提交的项目，再查询各自任务。`--only ink-bloom` 只处理指定 slug，`--timeout` 控制一次轮询等待秒数，默认 900。查询中断只重查原任务，提交失败或未知结果不自动重提。

每个镜头目录保留提示词、回执、`clip.mp4` 与三张抽帧图。已有 downloaded 结果直接跳过；改变提示词时必须改 slug。超过等待时间后，用相同目录和 `--poll-only` 继续查询。是否完成应看回执的 downloaded 状态与实际文件。

生成后核对实际内容、情绪、动作与裁后效果，再决定是否采用。预期表达没有实现时调整选段、换素材或弃用；仍有作用的结果更新实际采用理由，不能把请求里的意图直接当作完成结果。

## 免费商用实拍检索

默认推荐 Pixabay。Agent 按镜头的实际需要制定查询，从[检索模板](../templates/stock-brief.json)填写具体主体、动作和场景，再少量下载、逐条判断。将自己的 `PIXABAY_API_KEY` 填入本项目的 `.env.local`。查询默认使用英文，中文词可给对应镜头加 `"lang": "zh"`。[Pixabay 官方视频 API 与 Key 入口](https://pixabay.com/api/docs/)

```sh
python tools/stock_search.py --provider pixabay --brief projects/my-video/stock-brief.json --per-shot 2 --out projects/my-video/stock-pixabay
```

Pixabay 的相同查询在本地缓存 24 小时。按当前镜头需要搜索，避免批量抓库。每个镜头目录下的 `manifest.json` 记录候选 MP4、预览图、作者、原始页面和许可；向用户展示候选时附来源链接。零命中时调整描述或另行编排。检索和下载故障会返回错误，不能当作库中没有合适画面。

工具跳过 Pixabay 明确标为 AI 生成的视频，清单中的 `is_ai_generated` 记录平台标记，空值表示来源未提供该信息。按实际输出窗口查看候选的连续动作与前后镜头，并核对商标、可识别人物与本次使用场景。检索命中后也可以在授权预算内试做一个有明确改善目标的生成版，由 Agent 在同段口播下决定取舍。[Pixabay 素材许可](https://pixabay.com/service/license-summary/) · [选镜流程](../methods/制作流程.md#4-选镜头与补画面)

已有 Pexels 配置可以用同一命令传 `--provider pexels` 和单独的输出目录。旧配置仅含 `PEXELS_API_KEY` 且未声明 Pixabay 字段时，原命令仍使用 Pexels。显式选择的服务缺少 Key 会直接提示。[Pexels 视频 API](https://www.pexels.com/api/documentation/)
