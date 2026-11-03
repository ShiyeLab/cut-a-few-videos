# 验证与交付

## 离线检查

在仓库根目录运行，不使用服务 Key：

```sh
python tools/test_video_fixes.py
python -m unittest discover -s tests -v
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/check-v1
```

回归检查验证图片推近、叠化与片长、字幕完整性、流式音频拼接、配置入口、口播锚点、四种声音组合，以及服务凭证读取和中断恢复。生图工具使用模拟响应检查图片落盘、重复运行复用、未知结果保护与无效图片处理，不产生在线请求。

`verify.json` 中 `decode_ok`、`geometry_ok`、`audio_ok`、`duration_ok` 应全部为 true。声画时长容差为 0.06 秒；全静音片保留静音轨，所以 `audio_ok` 也为 true。`layout_report.json` 的 overflow 应为空。最终字幕的结束时间应覆盖片尾。

视频理解接入使用离线模拟检查任务提交、查询、结果复用、失败后不重提、输入变更及凭证隔离。另可用 `mediakit-cli video video-understand-router --schema` 与 `mediakit-cli shared query-task --schema` 核对安装版本的真实接口；这些检查不证明云端效果。实际制作须取得 completed 结果，阅读 `analysis.md`，将选段依据和不确定项写入素材清单后再编排。

## 实际看片

- 通看完整视频，核对每句含义与画面，特别是出现书名、翻页、抄写和情绪转折时。
- 看中央裁切后的主体，检查书封、书页和人物是否被错误裁掉。
- 看连续的推近过程和转场，检查跳位、折返、闪白、空帧或错误片段。
- 看最长字幕、标题和末句，确认无漏字、裁字、孤立标点或进入平台遮挡区。
- 听完整声音，核对词组连贯、自然换气、音乐音量和最后一字。
- AI 环境镜头逐条检查文字、手和书本是否意外出现；人物与实际运动是否符合镜头设计，是否与前后画面衔接，是否误作产品实拍。

交付同一版本的 MP4、配置和检查记录。自动通过、实际看片和用户确认分别记录。
