# Windows 离线安装说明

## 选择基础安装包

- **标准版（Standard）**：适合大多数电脑。内置 Python、FFmpeg、英译中/中译英快速离线翻译模型和字幕字体；体积更小。
- **完整版（Complete）**：在标准版基础上增加本地 Ollama 与 Qwen3:4b，用于更自然的本地段落翻译；需要更多磁盘空间和内存。

两个基础安装包都不再强制携带 Whisper 语音识别模型。安装基础程序后，请按电脑配置安装一个模型包：

- **Whisper Small**：大多数电脑推荐，速度较快，对内存和显存要求较低。
- **Whisper Medium**：识别质量更高，但需要更多内存、显存、磁盘空间与处理时间。

程序在开始字幕任务前会检测模型包。没有模型时会明确提示安装 Small 或 Medium，不会在后台偷偷下载。

## 安装顺序

1. 在 `dist` 中选择同一版本的 Standard 或 Complete 基础安装包。
2. 把该 `.exe` 与其全部同名 `.bin` 分卷放在同一个文件夹，不要重命名或遗漏分卷。
3. 双击基础安装包并完成安装。
4. 选择一个 Whisper 模型安装包：`Whisper-Small-Model-Setup.exe` 或 `Whisper-Medium-Model-Setup.exe`。
5. 把模型包安装到与基础程序相同的文件夹；默认位置通常正确。
6. 从开始菜单或桌面打开 **YouTube Chinese Localizer**。

Small 与 Medium 可以同时安装，软件会优先按你选择的处理方式和当前硬件使用合适的模型。只下载无字幕视频时不需要 Whisper 模型。

不要把不同安装包的 `.bin` 分卷混在一起。安装包未做代码签名时，Windows 可能显示来源提示；请只运行来自项目官方发布页并已核对哈希的文件。

## 本地 AI 大模型提示

“本地 AI 段落翻译”除 Whisper 外还需要 Qwen3:4b 大语言模型：

- 安装 **完整版**：Qwen3:4b 已内置，不需要 API Key，也不需要另行下载大语言模型。
- 安装 **标准版**：可直接使用快速离线翻译；如需段落 AI 翻译，请改装同一版本的完整版。

## 校验完整性

每个基础包和模型包都有对应的 SHA-256 清单。在 PowerShell 中进入文件夹后可运行：

```powershell
Get-FileHash .\YouTube-Chinese-Localizer-*-Setup* -Algorithm SHA256
```

将输出与对应 `SHA256SUMS-<版本>-*.txt` 清单逐行比较。安装基础程序后还可从开始菜单运行 **Verify YouTube Localizer Installation**，它会校验基础资产哈希、桌面界面和离线翻译模型。

## 开始任务前的自动预检

图形界面每次开始任务都会检查：

- 是否已安装适合的 Whisper 模型；
- 基础包层级和本地 AI 模型是否齐全；
- 可用磁盘空间是否足够存放源视频、音频、字幕和最终高质量输出；
- NVIDIA 显存或 CPU 内存是否适合当前模型。

缺少模型或空间不足时，任务会在下载前停止，并把详细结果写到项目目录的 `logs/preflight.json`。命令行可提前执行：

```powershell
python main.py preflight "D:\Videos\已授权的视频.mp4"
```

## 建议

- 追求最小下载量：安装标准版 + Whisper Small。
- 追求无 API 的自然段落翻译：安装完整版 + Whisper Small 或 Medium。
- 长视频尽量输出到本机 SSD，而不是 OneDrive 同步目录或移动硬盘。
- 仅下载无字幕最高质量视频时，选择“无字幕直接下载”；这不需要识别、翻译或重新编码。
