# Windows 离线安装说明

## 选择安装包

- **标准版（Standard）**：适合大多数电脑。内置 Whisper Small、英译中和中译英快速离线翻译模型、FFmpeg 和三款字幕字体。首次使用不下载模型。
- **完整版（Complete）**：在标准版基础上增加 Whisper Medium、本地 Ollama 和 Qwen3:4b，可进行更自然的本地段落翻译；需要更多磁盘空间和内存。

标准版不包含 Medium 或 Qwen 时，软件会在开始任务前自动改用已内置的 Small 和快速离线翻译，不会在后台联网下载模型。

## 安装

1. 在 `dist` 中选择同一版本、同一层级的一组文件。
2. 把 `.exe` 与其全部同名 `.bin` 分卷放在同一个文件夹，不要重命名或遗漏分卷。
3. 双击 `.exe`，按提示安装。
4. 从开始菜单或桌面打开 **YouTube Chinese Localizer**。

不要把 Standard 和 Complete 的分卷混在一起。安装包未做代码签名时，Windows 可能显示来源提示；请只运行来自项目官方发布页并已核对哈希的文件。

## 校验完整性

每个包都有专用的哈希清单：

- `SHA256SUMS-<版本>-standard.txt`
- `SHA256SUMS-<版本>-complete.txt`

在 PowerShell 中进入安装包文件夹后可运行：

```powershell
Get-FileHash .\YouTube-Chinese-Localizer-*-Offline-Setup* -Algorithm SHA256
```

将输出与对应清单逐行比较。安装后也可从开始菜单运行 **Verify YouTube Localizer Installation**，它会校验内置资产哈希、桌面界面和离线模型加载；该快捷方式不运行较慢的 Qwen 推理。

## 开始任务前的自动预检

图形界面每次开始任务都会检查：

- 安装包层级与本地模型是否齐全；
- 可用磁盘空间是否够存放源视频、音频、字幕和最终高质量输出；
- NVIDIA 显存或 CPU 内存是否适合当前模型；
- 是否需要使用安全的 Small/CPU/快速离线翻译回退方案。

空间不足时任务会在下载前停止，并把详细结果写到项目目录的 `logs/preflight.json`。命令行可提前执行：

```powershell
python main.py preflight "D:\Videos\已授权的视频.mp4"
```

## 建议

- 需要最快、最省空间的本地处理：选择标准版。
- 需要无 API 的自然段落翻译，且电脑有较充足的内存、显存和磁盘空间：选择完整版。
- 长视频尽量输出到本机 SSD，而不是 OneDrive 同步目录或移动硬盘。
- 仅下载无字幕最高质量视频时，选择“无字幕直接下载”；这不需要识别、翻译或重新编码。
