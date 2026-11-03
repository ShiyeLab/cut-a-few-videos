# 验证与交付

## 离线检查

在仓库根目录运行，不使用服务 Key：

```sh
python tools/test_video_fixes.py
python -m unittest discover -s tests -v
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/check-v1
```

回归检查验证运镜匀速无停顿（含从最终成片逐帧测量）、各转场起止平滑、转场不吞片长、字幕完整性、流式音频拼接、配置入口、口播锚点、四种声音组合，以及服务凭证读取和中断恢复。生图工具使用模拟响应检查图片落盘、重复运行复用、未知结果保护与无效图片处理，不产生在线请求。

`verify.json` 中 `decode_ok`、`geometry_ok`、`audio_ok`、`duration_ok` 应全部为 true。声画时长容差为 0.06 秒；全静音片保留静音轨，所以 `audio_ok` 也为 true。`layout_report.json` 的 overflow 应为空。最终字幕的结束时间应覆盖片尾。

视频理解接入使用离线模拟检查任务提交、查询、结果复用、失败后不重提、输入变更及凭证隔离。另可用 `mediakit-cli video video-understand-router --schema` 与 `mediakit-cli shared query-task --schema` 核对安装版本的真实接口；这些检查不证明云端效果。实际制作须取得 completed 结果，阅读 `analysis.md`，将选段依据和不确定项写入素材清单后再编排。

## 实际看片

- 通看完整视频，核对每句含义与画面，特别是出现书名、翻页、抄写和情绪转折时。
- 看中央裁切后的主体，检查书封、书页和人物是否被错误裁掉。
- 看连续的运镜过程和转场，检查跳位、折返、一顿一顿、空帧或错误片段。
- 看最长字幕、标题和末句，确认无漏字、裁字、孤立标点或进入平台遮挡区。
- 听完整声音，核对词组连贯、自然换气和最后一字。
- 多条成片时核对 `brief.md` 差异表与实际成片一致。
- AI 环境镜头逐条检查文字、手和书本是否意外出现；人物与实际运动是否符合镜头设计，是否与前后画面衔接，是否误作产品实拍。

交付同一版本的 MP4、配置和检查记录。自动通过、实际看片和用户确认分别记录。

## 剪映草稿

### 正式导出

`build_video.py` 合成完成后自动导出（`--no-jianying` 跳过）；对已有输出目录补导出用 `python tools/jianying_draft.py --work <输出目录>`，加 `--prepare-only` 准备的目录也可以。剪映开着时只生成草稿文件并记入待登记清单，退出剪映后 `python tools/jianying_draft.py --register` 一次登记全部。找不到剪映草稿目录或导出失败时只给出提示，不影响已完成的 MP4。工具读取同一目录的 `compose_args.json`、`layout.json`、`shots.json`、`subs.json` 与 `layout_report.json`，生成六条轨道：中央窗画面在最下层，上面是挖空中央窗的底图，再上是标题、底部文字、字幕三条文字轨和配音轨。

- 中央窗按镜头的 `fit` 与 `focus_y` 放大和取景，超出部分由底图遮住，与成片的裁切一致；`blur` 在草稿里按 `contain` 处理。视频片段静音，源区间与速度沿用镜头表。
- 镜头之间硬切，不带 `move` 运镜与转场；文字用剪映默认字体，字号按像素 ÷ 10.8 换算，为近似值。
- 素材复制进草稿目录，草稿不依赖项目文件的位置。

打开草稿后核对：镜头切点与 MP4 一致，中央窗取景与成片接近，标题、底部文字与每句字幕齐全可改，配音完整。

### 兼容性测试

环境需已安装 `requirements.txt` 中的依赖及 FFmpeg。先启动一次 Mac 剪映以建立草稿目录，再完全退出剪映，在仓库根目录执行：

```sh
python tools/jianying_smoke.py
```

工具生成一个 1080×1920、30 fps、6 秒草稿，包含底图、中央视频、标题、字幕、音频五条轨道。标题与两句字幕为原生可编辑文字；音频是 440 Hz 测试音。媒体均由程序生成并放在新草稿内，不调用外部服务。

每次生成独立工程 ID，正文、元数据和首页条目保持一致。工具备份 `root_meta_info.json` 后登记 Mac 首页，保留已有条目；剪映运行中或索引发生变化时停止登记。自定义位置用 `--draft-root`；仅生成文件、不修改首页时加 `--no-register`，目标目录须已存在。

重新启动剪映，从首页打开 `cut-smoke-…` 草稿，依次验证：

1. 五条轨道齐全，图片、视频、声音没有丢失。
2. 修改标题和两句字幕，确认预览实际更新。
3. 返回首页后重新打开，确认修改保留。
4. 在剪映本地导出 MP4，检查 0—3 秒与 3—6 秒的字幕、完整标题、画面和音频；导出分辨率与编码以剪映导出面板为准。

测试草稿只验证本机剪映能否打开生成的草稿。其他平台及剪映版本须按上述步骤重新验证。剪映保存后的工程文件由剪映管理，两个工具每次都新建草稿，不会覆盖已编辑的草稿。

ID、首页登记、索引备份、轨道与时间换算的自动测试：

```sh
python -m unittest discover -s tests -p test_jianying.py -v
```
