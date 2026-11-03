# 开源依赖、技术参考与署名

感谢以下项目的作者与贡献者。本页标明直接依赖、间接依赖和技术参考各自承担的工作。Python 直接依赖版本以 [requirements.txt](requirements.txt) 为准；具体许可证以对应版本随包提供的文件为准。

## 直接使用

| 项目与维护者 | 本项目中的用途与入口 | 许可证 |
| --- | --- | --- |
| [FFmpeg / ffprobe](https://ffmpeg.org/)，FFmpeg contributors | [compose.py](tools/compose.py) 等调用外部命令，完成素材探测、裁剪、运镜、转场、混音、编码和检查 | [LGPL-2.1-or-later；启用 GPL 组件时按相应 GPL 许可](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md)。实际许可随安装版本和编译选项确定 |
| [Pillow](https://github.com/python-pillow/Pillow)，Jeffrey A. Clark 与贡献者；源自 PIL / Fredrik Lundh / Secret Labs AB | [layout.py](tools/layout.py) 绘制标题与字幕；离线教学例生成图片；剪映测试生成封面。直接安装版本 12.3.0 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| [AI MediaKit CLI](https://github.com/volcengine/mediakit-cli)，Volcengine | [understand_video.py](tools/understand_video.py) 调用视频理解与异步任务查询；接入方式参考官方 CLI 和 Skills 文档 | [MIT](https://github.com/volcengine/mediakit-cli/blob/main/LICENSE)；云端能力另按服务条款使用 |
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)，GuanYixuan 与贡献者 | [jianying_smoke.py](tools/jianying_smoke.py) 生成视频、原生文字和音频轨道，用于可编辑剪映草稿测试。直接安装版本 0.3.1 | [Apache-2.0](https://github.com/GuanYixuan/pyJianYingDraft/blob/main/LICENSE) |
| [思源宋体 / Source Han Serif](https://github.com/adobe-fonts/source-han-serif)，Adobe 与字体贡献者 | 通用布局的中文字体；由使用者下载到 `local/fonts/`，可替换 | [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-serif/blob/release/LICENSE.txt) |

## 技术参考

| 项目与作者 | 参考范围 | 许可证与接入情况 |
| --- | --- | --- |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)，Harry / harry0703 与贡献者 | 自动化短视频流程、素材检索、配音、字幕与合成的功能组织；参考其项目说明和 CLI 接口 | [MIT](https://github.com/harry0703/MoneyPrinterTurbo/blob/main/LICENSE)。属于方案和接口参考，当前制作入口不调用该项目 |
| [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)，Vincentwei1021 与贡献者 | [剪映导出技术说明](https://github.com/Vincentwei1021/video-shotcraft/blob/main/references/jianying-export.md)：原生文本与媒体分轨、字号与坐标、Mac 草稿安装及打开后验证的方法 | [Apache-2.0](https://github.com/Vincentwei1021/video-shotcraft/blob/main/LICENSE)。属于技术文档参考，当前仓库未引入其 Remotion 渲染链、模板或音频素材 |

## 剪映草稿库的间接依赖

以下依赖由 pyJianYingDraft 的安装链引入，版本由安装环境解析；它们不是独立的制作服务。

| 项目 | 用途 | 许可证 |
| --- | --- | --- |
| [pymediainfo](https://github.com/sbraz/pymediainfo) | 读取媒体信息 | [MIT](https://github.com/sbraz/pymediainfo/blob/master/LICENSE) |
| [MediaInfoLib](https://github.com/MediaArea/MediaInfoLib)，MediaArea.net | pymediainfo 调用的媒体探测库 | [BSD-2-Clause 及上游列出的其他许可选项](https://github.com/MediaArea/MediaInfoLib/blob/master/License.html) |
| [ImageIO](https://github.com/imageio/imageio) | 图片读取 | [BSD-2-Clause](https://github.com/imageio/imageio/blob/master/LICENSE) |
| [NumPy](https://github.com/numpy/numpy) | ImageIO 使用的数组支持 | [BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt)；安装包内附带组件的声明见随包许可 |
| [Python-UIAutomation-for-Windows](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows)，yinkaisheng 与贡献者 | 上游在 Windows 上声明的条件依赖；本项目的草稿生成脚本不调用其 UI 自动导出功能 | [Apache-2.0](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows/blob/master/LICENSE) |

## 服务与媒体来源

豆包配音、Seedream、MiniMax 和 Pexels 是外部服务接入，使用方式见[服务选择与替换](docs/optional-services.md)。MediaKit 的开源 CLI 许可也不替代其云端服务条款。Pexels 素材按[素材许可](https://www.pexels.com/license/)记录来源与用途。

本仓库通过依赖安装或外部命令使用上述软件，不附带其源码、二进制、字体包、账户配置或第三方媒体包。教学输入由程序生成几何图形、测试画面与合成音。使用者加入的媒体在 `sources.json` 中记录来源、作者、用途与许可。

新增依赖或借鉴其他项目时，同步更新本页与 README；直接引入第三方代码时，在相应文件标明来源、版本和修改，并保留该版本要求的版权、LICENSE 与 NOTICE。署名说明不替代随包的完整许可文件。
