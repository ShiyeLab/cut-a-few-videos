# 开源依赖与署名

感谢以下项目的作者与贡献者。本页列出当前功能直接调用的软件及媒体探测依赖，并标明用途和代码入口。Python 直接依赖版本以 [requirements.txt](requirements.txt) 为准；完整安装依赖和许可证以对应版本的包元数据及随包文件为准。

## 直接使用

| 项目与维护者 | 本项目中的用途与入口 | 许可证 |
| --- | --- | --- |
| [FFmpeg / ffprobe](https://ffmpeg.org/)，FFmpeg contributors | [compose.py](tools/compose.py) 等调用外部命令，完成素材探测、裁剪、运镜、转场、混音、编码和检查 | [LGPL-2.1-or-later；启用 GPL 组件时按相应 GPL 许可](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md)。实际许可随安装版本和编译选项确定 |
| [Pillow](https://github.com/python-pillow/Pillow)，Jeffrey A. Clark 与贡献者；源自 PIL / Fredrik Lundh / Secret Labs AB | [layout.py](tools/layout.py) 绘制标题与字幕；离线教学例生成图片；剪映测试生成封面。直接安装版本 12.3.0 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| [AI MediaKit CLI](https://github.com/volcengine/mediakit-cli)，Volcengine | [understand_video.py](tools/understand_video.py) 的 `call_cli()` / `run()` 调用 `video video-understand-router` 与 `shared query-task`，完成视频理解接入 | [MIT](https://github.com/volcengine/mediakit-cli/blob/main/LICENSE)；云端能力另按服务条款使用 |
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)，GuanYixuan 与贡献者 | [jianying_draft.py](tools/jianying_draft.py) 的 `build()` 把合成产物转成视频、原生文字和音频轨道的可编辑剪映草稿；[jianying_smoke.py](tools/jianying_smoke.py) 生成兼容性测试草稿。直接安装版本 0.3.1 | [Apache-2.0](https://github.com/GuanYixuan/pyJianYingDraft/blob/main/LICENSE) |

## 采用的实现

| 项目与作者 | 采用内容与入口 | 许可证 |
| --- | --- | --- |
| [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)，Vincentwei1021 与贡献者 | [剪映导出说明](https://github.com/Vincentwei1021/video-shotcraft/blob/main/references/jianying-export.md)中的两条做法：像素字号 ÷ 10.8 换算剪映字号（[jianying_draft.py](tools/jianying_draft.py) 的 `PX_PER_SIZE`），以及把媒体放进草稿目录以适应 Mac 剪映沙盒（`build()` 复制素材）。未引入其代码 | [Apache-2.0](https://github.com/Vincentwei1021/video-shotcraft/blob/main/LICENSE) |

## 草稿媒体探测依赖

`jianying_draft.py` 与 `jianying_smoke.py` 创建图片、视频和音频片段时，pyJianYingDraft 0.3.1 的 `local_materials.py` 中 `VideoMaterial` / `AudioMaterial` 调用以下组件读取媒体尺寸、轨道及实际时长。

| 项目 | 用途 | 许可证 |
| --- | --- | --- |
| [pymediainfo](https://github.com/sbraz/pymediainfo) | 读取媒体信息 | [MIT](https://github.com/sbraz/pymediainfo/blob/master/LICENSE) |
| [MediaInfoLib](https://github.com/MediaArea/MediaInfoLib)，MediaArea.net | pymediainfo 调用的媒体探测库 | [BSD-2-Clause 及上游列出的其他许可选项](https://github.com/MediaArea/MediaInfoLib/blob/master/License.html) |

## 服务与媒体来源

豆包配音、Seedream、MiniMax 和 Pexels 是外部服务接入，使用方式见[服务选择与替换](docs/optional-services.md)。MediaKit 的开源 CLI 许可也不替代其云端服务条款。Pexels 素材按[素材许可](https://www.pexels.com/license/)记录来源与用途。

本仓库通过依赖安装或外部命令使用上述软件，不附带其源码、二进制、字体包、账户配置或第三方媒体包。教学输入由程序生成几何图形、测试画面与合成音。使用者加入的媒体在 `sources.json` 中记录来源、作者、用途与许可。

新增署名须能对应到实际调用的代码入口或明确采用的实现；仅检索、查阅或评估过的项目不列为使用或借鉴来源。直接引入第三方代码时，在相应文件标明来源、版本和修改，并保留该版本要求的版权、LICENSE 与 NOTICE。署名说明不替代随包的完整许可文件。
