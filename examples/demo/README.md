# 8 秒离线教学例

这是合成工具的最小完整输入：一张几何图、一段动态测试画面、同一张上下贴片底图，以及三条字幕。几何图、底图、视频和和弦由 [make_inputs.py](make_inputs.py) 生成，使用 Pillow 自带的英文字体，无外部素材。

```sh
python examples/demo/make_inputs.py
python tools/build_video.py --project examples/demo/project.json --work projects/demo/v1
```

全部命令从仓库根执行。结果在 `projects/demo/v1/video.mp4`，8 秒、1080×1920、30 fps；带合成音，没有人声。

| 输入 | 内容 |
| --- | --- |
| [project.json](project.json) | 标题、路径、时长、转场和音乐参数 |
| [script.txt](script.txt) | 三句英文教学字幕 |
| [timeline.json](timeline.json) | 人工指定的教学时间轴，无口播时使用 |
| [scenes.json](scenes.json) | 句首到画面、选段和推近的对应 |
| `generated/` | 命令生成的输入和英文版布局，不进入 Git |

先改标题，再输出 `v2`，可以看到标题变化而底图不变。再把某镜的 `zoom` 改为 0，对照居中推近与静止的区别。加 `--no-music` 得到全静音版。

教学例的英文字幕与手工秒数仅为无需配音、无需字体包即可运行。正式中文视频换上自己的中文字体、完整口播、配音与真实时间轴，步骤见[使用说明](../../docs/getting-started.md)。
