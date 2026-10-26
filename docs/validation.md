# 验证与交付

## 离线检查

在仓库根目录运行，不使用服务 Key：

```sh
python tools/test_video_fixes.py
python -m unittest discover -s tests -v
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/check-v1
```

原有回归检查验证：图片推近的连续位移、叠化确实混合且不缩短片长、截短文件被拒绝、字级时间与文字对应、演绎要求与正文分离、流式音频拼接和服务错误。发布整理增加的检查针对通用配置入口、口播锚点、四种声音组合与本地凭证读取。

`verify.json` 中 `decode_ok`、`geometry_ok`、`audio_ok`、`duration_ok` 应全部为 true。声画时长容差为 0.06 秒；全静音片保留静音轨，所以 `audio_ok` 也为 true。`layout_report.json` 的 overflow 应为空。最终字幕的结束时间应覆盖片尾。

## 实际看片

- 通看完整视频，核对每句含义与画面，特别是出现书名、翻页、抄写和情绪转折时。
- 看中央裁切后的主体，检查书封、书页和人物是否被错误裁掉。
- 看连续的推近过程和转场，检查跳位、折返、闪白、空帧或错误片段。
- 看最长字幕、标题和末句，确认无漏字、裁字、孤立标点或进入平台遮挡区。
- 听完整声音，核对词组连贯、自然换气、音乐音量和最后一字。
- AI 环境镜头逐条检查文字、手、人物和书本是否意外出现。

交付同一版本的 MP4、配置和检查记录。自动通过、实际看片和用户确认分别记录。

## 本次整理的验证范围

2026-10-26，在 Python 3.12.14、Pillow 12.3.0 和 FFmpeg 8.1.1 的 macOS 环境核对。实际结果见[发布验证记录](release-check.json)。离线教学例在仅含上传清单文件的独立目录重新生成输入并合成；核对 8 秒片长、1080×1920、30 fps、末句与抽帧。在线服务没有重新调用。

上传文件由[明确清单](publish-files.txt)限定。检查文档相对链接、代码导入与示例依赖；扫描私人路径、凭证样式、临时鉴权链接、回执和意外二进制。生成目录与本地素材不进入清单。
