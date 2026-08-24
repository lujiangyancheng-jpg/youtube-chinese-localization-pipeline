# 参与 Video Localizer

感谢你愿意帮助完善这个项目。不会写代码也完全可以参与：不同硬件上的测试结果、字幕质量反馈、说明书修正和可复现的故障报告都很有价值。

## 从哪里开始

- 使用中遇到问题：先按 [15 分钟测试清单](docs/TESTING_GUIDE.zh-CN.md) 复测，再提交 [Bug 报告](https://github.com/lujiangyancheng-jpg/video-localizer/issues/new?template=bug_report.yml)。
- 想讨论用法或还不确定是不是 Bug：使用 [Discussions](https://github.com/lujiangyancheng-jpg/video-localizer/discussions)。
- 有产品想法：提交 [功能建议](https://github.com/lujiangyancheng-jpg/video-localizer/issues/new?template=feature_request.yml)，说明具体工作流，而不只是功能名称。
- 想贡献代码或文档：查看 `good first issue` 和 `help wanted` 标签，也可以先在对应 Issue 下留言认领。

请勿在公开 Issue 中上传视频、字幕正文、API Key、Cookie、访问令牌或含个人路径的完整日志。桌面程序的“导出诊断包”会生成经过脱敏的信息，优先使用它。

## 本地开发

推荐 Windows 10/11、Python 3.12、Git、FFmpeg。仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,transcription]"
python -m ruff check src tests
python -m pytest -q
```

界面可通过以下命令启动：

```powershell
python -m youtube_localizer.gui
```

只有确实需要验证字幕压制时才运行 FFmpeg 集成测试：

```powershell
python -m pytest -q -m integration
```

## 修改原则

- 一个 Pull Request 解决一个明确问题；避免同时做无关重构。
- 保持下载、识别、翻译、渲染各阶段可恢复，不要破坏已有项目的断点续跑。
- 网络输入必须维持现有安全边界：不绕过 DRM、登录、付费、地区或平台访问控制，不读取日常浏览器凭据。
- 新功能需要覆盖正常路径和失败恢复；用户可见的变化同时写入 `CHANGELOG.md` 和相关说明。
- 不要提交模型、视频、构建目录、安装包、密钥或私人日志。

## 提交 Pull Request

1. Fork 仓库并从最新 `main` 创建分支。
2. 完成修改、测试和文档更新。
3. 在 PR 中写明“解决什么问题、如何验证、有什么风险或限制”。界面修改请附截图。
4. 确认 Windows quality gate 通过。维护者会根据可复现性、兼容性、安全边界和维护成本进行评审。

提交贡献即表示你同意按仓库的 [MIT License](LICENSE) 提供该贡献。请只使用你有权分享的代码、素材和测试数据。
