# SEM Legend

轻量、本地运行的 SEM 图像整理工具。Tkinter 桌面 GUI，无服务器、无账号、无需 GPU。原始图像不会被覆盖。

## 下载与启动

Windows 用户可从 [GitHub Releases](https://github.com/SekiroYoumu/sem-legend/releases/latest) 下载 `SEM-Legend-0.1.1-windows-x64.zip`，解压整个文件夹后双击 `SEM-Legend.exe`。免安装包自带 Python 和运行依赖，使用时无需联网；请保留旁边的 `_internal` 文件夹。图像默认导出到程序旁边的 `output`，请放在可写的目录运行。

源码用户按下列步骤启动：

安装 Python 3.10 或更新版本（含 Tkinter），双击 **install.bat** 安装依赖，然后双击 **start.bat**，或运行：

```powershell
python app.py
```

首次在其他电脑使用：安装带 Tkinter 的 Python 3.10 或更新版本，双击 `install.bat` 安装依赖，再启动。仅依赖 Pillow、NumPy、tkinterdnd2。缺少拖拽组件时仍可通过按钮导入导出。

## 样例目录

**公开仓库与发布包仅附 4 张可再分发的图片**：Cu Catalyst、Nanosigaret、JEOL NeoScope 贝壳及 Silver Nanowires。共 2 张自动识别、2 张需核对；图片保持原样，作者、来源、许可和 SHA-256 见 `example/SAMPLES.json` 中的 `redistributable: true` 条目。图片许可独立于程序代码的 MIT 许可，分别遵循 CC BY 4.0、CC BY-SA 3.0/4.0；再分发或修改图片时请保留署名、来源并遵守对应许可：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)、[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)、[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。

以下完整数据分类说明针对开发者本地评估集，不代表所有图片随公开包分发：

`example` 已整理为 **10 类、14 张精选图片，每类 1–2 张**，包含自动通过、需核对和无标尺反例。分类与预期结果见 [样例说明](example/README.md)，逐图来源见 [SAMPLES.json](example/SAMPLES.json)。点击「载入样例」只扫描这个精选目录。

用户原先提供的完整 14 张 TIFF 保存在 `example_archive/original_user_examples`，内容未改动；完整网络回归资源保存在 `validation_output`，不加入日常样例队列。回归脚本优先使用归档，避免为简化演示而丢失测试覆盖。

## 使用

1. 拖入图像/文件夹，或点击「添加图像」「载入样例」。文件夹会递归导入。支持 TIFF、PNG、JPEG、BMP。
2. 查看队列中的尺度来源。Zeiss TIFF 优先使用 `Image Pixel Size`，FEI TIFF 读取私有 TIFF 标签中的 `PixelWidth`。程序还会独立识别原标尺文字与横线，交叉核对尺度。有清晰匹配的原标尺时，缺少元数据的图像也可自动校准。实测布局见下面的兼容性表。
3. **「自动识别」可直接导出，「需核对」需确认**：在「标尺 → 查看自动识别依据」检查文字框、刻线、匹配分数和尺度差异。有歧义、元数据冲突或系统 OCR 建议值需要人工核对像素尺寸，再点击「应用到当前图像」。没有识别成功时，可输入已知 nm/像素；或输入原标尺真实长度，切到「画线校准」，在原始图像连接原标尺两端。尺度不会从另一张图或文件名自动推断。
4. 「图像」中默认检测底部黑色、灰色或网格信息栏并裁剪；不确定时保留原图。需要自定义时，切换「框选裁剪」，在原图框选。清除手动裁剪可恢复自动方式。
5. 「逐图自动」按图像主体的百分位拉伸灰度，再应用亮度、对比度、Gamma；「固定黑白场」使整批使用同一映射；「保留原始」关闭自动拉伸，亮度/对比度/Gamma 的默认值不会改变 8 位灰度。整批比较时可使用固定黑白场，避免把真实强度差异强行拉平。百分位拉伸会截断指定比例的暗亮像素，参数和实际黑白场写入记录。
6. 标尺默认左下白色、文字在上。默认字号保持为图高的 **6.75%**。长度为 0 时，自动标尺至少占图宽的 **12%**（此前 24% 的一半），再向上选取 1/2/5 系列物理长度；由于取整，实际横条长度不一定恰好减半。可修改「自动最小长度 / 图宽」，手动指定的物理长度优先。可调整位置、字体、线宽、描边和边距，输出缩放时同步更新像素尺度。读取旧预设会保留预设中明确指定的参数。
7. 「导出」选择目录，导出当前图像或全部队列。Windows 下可点击「复制当前图片到剪贴板」，将当前参数下的处理结果作为图片复制，直接粘贴到 Word、PowerPoint 等应用；复制使用实际输出尺寸，包含裁剪、调色和标尺，不包含界面或预览背景。也可从「按住这里拖出当前结果」拖入资源管理器或支持接收文件的应用；拖出为当前参数下的 PNG 临时文件，程序退出时会清理，请先完成目标应用的复制。正式导出应使用导出按钮，获得完整记录。

全局图像/标尺参数作用于整批；手动尺度和裁剪范围只作用于对应图像。预设仅保存全局参数，避免把某张图的尺度错误应用到其他倍率的图像。预览结果自动更新；数值输入后按 Enter 或离开输入框。滚轮可放大预览。

## 输出

- PNG 或 LZW 无损压缩 TIFF，均为 8 位灰度。
- 每图一份 JSON：原文件、裁剪范围、尺度来源、输入和输出像素尺寸、调色参数、实际标尺像素长度及舍入误差。
- 每批一份 CSV：成功/失败文件及原因。个别失败不会阻断其他图像。
- TIFF 写入物理分辨率，便于 Fiji/ImageJ 读取；PNG 的物理尺度以 JSON 为准。
- 同名结果自动编号，不覆盖已有结果。默认输出到项目 `output` 文件夹。

## 实测兼容的标尺种类

按**实际图像布局和识别结果**划分，不表示支持某厂商所有型号和导出设置。「自动」可直接导出；「需核对」表示已找到横线和建议尺度，但字符仍有歧义，必须检查后点击「应用到当前图像」。测试环境为当前 Windows 系统字体。

| 来源 / 样例 | 标尺种类与位置 | 无元数据的实测结果 | 信息栏裁剪 |
|---|---|---|---|
| Zeiss GeminiSEM，原有 11 张样例 | 左下 H 形端点刻线，上方斜体文字，2/10/20 µm | **自动** | 自动 |
| JEOL，新增 `4.tif`、`5.tif`、`6.tif` | 底部中间白色实心横条，右侧等宽衬线文字，100/10/10 µm；支持粘连的 µm | **自动，3/3** | 自动 |
| FEI Helios NanoLab 660，RosettaSciIO 8 位及 16 位 TIFF | 右下两段水平线，500 µm 文字在中间，外侧有端点 | **自动**；两种位深是同一信息栏，不算两个独立场景 | 自动识别网格信息栏 |
| FEI Nova NanoSEM，`Cu Catalyst` | 右下中间文字分段线，5 µm | **自动** | 自动 |
| FEI Nova NanoSEM 450，`Nanosigaret` | 图像左下嵌入白色实心横条，上方 500 nm 文字，无信息栏 | **自动** | 保留图像 |
| FEI/EMScaleBarTools 原始面板截图 | 右下中间文字细线，100 µm | **需核对** | 截图灰色信息栏目前保留，可手动裁剪 |
| JEOL NeoScope JCM-5000，贝壳样例 | 下方白色横条，右侧 20 µm 文字 | **需核对**，µ 与其他字符的匹配仍有歧义 | 自动移除文字密集的黑色信息栏；本样例裁剪至 1280 × 1024 |
| `Silver Nanowires`，仪器型号未确认 | 右下浅色纹理背景上的白色横条，下方 1 µm 文字 | **需核对** | 保留图像 |
| TESCAN MIRA 4，Jeremy Poole 图库 3 个版本 | 灰色信息栏右下 U 形细线、左上 U 形细线、右下 U 形细线，上方 500 µm | **需核对，3/3 可定位并读出建议文字**；含约 1 像素倾斜的横线 | 灰色信息栏版本自动裁剪；嵌入版本保留 |
| EMScaleBarTools 处理后面板截图 | 白底框中的黑色实心横条，下方黑字 50 µm | **需核对**；这是处理后示例，不作为原始仪器验证 | 保留图像 |

单位解析支持 `nm`、`µm`、`μm`、`um`、`mm`、`pm`，以及小数点/小数逗号。真实样例目前主要覆盖 nm 与 µm；其他单位主要由合成测试覆盖。**不会把 `pm` 强行改成 `µm`。**

尚未确认通用支持：Hitachi/TESCAN 等仪器的分段尺规或点阵尺、垂直或明显倾斜的标尺、彩色标尺、旋转文字、多面板含多个尺度、严重模糊或压缩、单位缺失、文字仅在图注中的图像。这些情况使用手动画线校准；缺少尺度时不会猜测物理尺寸。黑色标尺当前针对白底框，任意亮色纹理背景未验证。

## 识别方法与限制

原标尺文字使用系统字体生成的数字、单位模板识别，不从样例图片提取模板、不读取文件名猜尺度，不下载模型。支持 Arial、Courier、Tahoma 等系统字体，扩展了小字号和大字号模板；对粘连字符尝试切分，检测居中文字的两段横线、带端点细线与实心条，并同时检查白字和黑字。字符匹配使用 NumPy 批量计算，保持 Pillow + NumPy 的依赖规模。

识别使用两种二值化阈值保留缩放后的小字笔画，浅色背景采用更高阈值；检查最低字符形状分数和次选差值。不同高匹配结果冲突时不自动接受。**匹配分数不是统计准确率。** 分数不足但文字格式有效时只给建议值，必须人工核对。系统 OCR 作为后备也只给需核对结果，不会擅自改写数字或物理单位。

元数据和光学尺度不一致时保留两种依据，要求核对，不静默选择其中之一。交叉核对容差为 `max(3%, 1.5 / 原标尺像素长度)`，用于容纳短标尺的像素量化误差。只有原标尺时，像素尺寸为「物理长度 / 两端刻线中心距离」；原标尺很短时会有相应的测量误差。

高位深 TIFF 会映射到 8 位显示范围，记录中注明；这个工具用于制图导出，定量分析应保留并使用原始文件。多页 TIFF 目前处理第一页。

没有信息栏的嵌入式原标尺不会自动被擦除，也不会凭空修补标尺遮挡的样品区域；需要避免新旧标尺重复时，可用框选裁剪去掉旧标尺。灰色栏裁剪和小字号线长测量仍应通过原图对比检查。

## 兼容性验证与样例来源

本轮将 **14 张用户样例 + 11 张网络样例**另存成**不保留任何元数据的 PNG**后识别：18 张自动通过、7 张给出需核对的建议，标尺文字均与人工读取一致。另外 3 张无可见标尺的 navcam 反例均未被赋予尺度。它们并非 25 个独立仪器场景：Helios 两张为同内容不同位深，MIRA 三张为同一对象的不同处理版本，另有两张裁自工具截图。这个小样本回归结果不能当作全厂商准确率或泛化保证。

Zeiss 有元数据的 10 张图，原标尺光学尺度与元数据差异小于 0.5%；Helios 测试图约 1.16%，包含小图上刻线端点的像素量化误差。其余无独立元数据的样例验证了文字与横线定位，不能据此宣称绝对尺度误差小于某个百分比。

网络样例作为本机评估资料与程序运行依赖分开保存：本地精选副本在 `example`，完整网络资源在被忽略的 `validation_output`；公开包仅含上文列出的 4 张允许再分发的图片。来源、作者、许可、下载地址与 SHA-256 保存在 `tests/compatibility_sources.json`，精选副本另见 `example/SAMPLES.json`。重新运行完整回归需要归档和这些可选资源。

- [RosettaSciIO FEI TIFF 测试集](https://github.com/hyperspy/rosettasciio/blob/main/rsciio/tests/test_tiff.py)：Helios E-beam 8/16 位及无可见标尺的 navcam 反例。E-beam 图的样品区域已置黑，仅仪器信息栏可用于本次识别验证。
- [EMScaleBarTools](https://github.com/lukmuk/em-scalebartools)：原图和处理结果截图各裁一个图像面板，裁剪坐标记录在来源清单中，不把截图当作原始 TIFF。
- [Cu Catalyst](https://commons.wikimedia.org/wiki/File:Cu_Catalyst.jpg)：SvenOras，CC BY 4.0。
- [Nanosigaret](https://commons.wikimedia.org/wiki/File:Nanosigaret.png)：Mikk Vahtrus，CC BY 4.0，来源说明为 FEI Nova NanoSEM 450。
- [Silver Nanowires](https://commons.wikimedia.org/wiki/File:Silver_Nanowires.jpg)：Maido Merisalu，CC BY-SA 4.0。
- [Aragonite layers in a blue mussel shell](https://commons.wikimedia.org/wiki/File:Aragonite_layers_in_a_blue_mussel_shell.jpg)：Glenn Elert，CC BY-SA 3.0，JEOL JCM-5000。
- [Jeremy Poole 的 TESCAN MIRA 图库](https://www.jeremypoolesem.org.uk/miragalleries.html)：Jeremy Poole，作者版权，下载仅用于本地兼容性评估，不随软件分发。

`tools/benchmark_compatibility.py` 输出逐图 CSV、识别依据 JSON、去元数据输入、自动通过的处理结果和标尺对照图。`tools/benchmark_recognition.py` 另外测试 JPEG 质量 85 与 1.5 倍缩放；这类变换测试不能增加独立样本数。

## 无界面批处理（可选）

```powershell
python batch.py example --output output
python batch.py example --output output_without_bar --no-bar
```

需要核对 OCR 或缺少尺度时，带标尺的命令行导出会失败并记录原因；通过 GUI 校准后导出即可。

## 验证

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/benchmark_compatibility.py
python tools/smoke_gui.py
```

测试覆盖字号和最小标尺默认值、Zeiss/JEOL/FEI 布局、两种位深、去元数据识别、粘连字符、未出现在样例中的数值和单位、无可见标尺的反例、模糊单位拦截、尺度冲突拦截、裁剪、灰度保持、缩放后的物理尺度、TIFF 校准写入和重复文件保护。私有归档或可选网络样例不存在时，对应测试会跳过，不自动联网。公开包可独立运行其余测试。完整 GUI 批量回归脚本依赖开发者本地的原始 TIFF 归档。

## 构建发布包

在 Windows x64 上使用独立构建环境，避免打入开发环境中的无关依赖：

```powershell
python -m venv .build/venv
.build/venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.build/venv/Scripts/python.exe tools/build_release.py
```

脚本生成 `dist` 下的源码 ZIP、Windows x64 便携 ZIP 和 `SHA256SUMS.txt`，并运行实际 EXE 的 GUI/拖拽/样例识别检查。只需要源码包时加 `--source-only`。打包使用文件白名单和样例清单，不包含 `.vendor`、原始数据归档、输出、缓存或本地评估资料。便携包附第三方依赖许可和实际构建版本；当前验证目标为 Windows 10/11 x64。

代码按 [MIT 许可](LICENSE) 发布；图片遵循各自许可。版本变化见 [CHANGELOG.md](CHANGELOG.md)。
