# 发布验收清单（开发版）

每一个公开 Windows Release 都应按以下顺序执行。生成的模型、暂存目录和安装包不提交 Git。

1. 在隔离环境运行 `ruff` 与完整 `pytest`。
2. 构建 Standard、Complete、Whisper Small 与 Whisper Medium；验证每个 `.exe` 与所有 `.bin` 分卷的 SHA-256。
3. 对每个基础包执行独立安装验证；Complete 必须执行一次真实本地 Qwen 推理。基础包加对应 Whisper 模型包后，必须验证模型可离线加载。
4. 测试默认安装目录，以及含空格和 Unicode 字符的自定义安装目录。检查开始菜单快捷方式指向 `Localize Studio.exe`，并运行 `Localize Studio.exe --verify`。
5. 如果持有正式代码签名证书：在生成基础安装包时传入 `-CertificateThumbprint`，并为单独的 Whisper 模型包传入同名参数。构建脚本会在写入 SHA-256 清单前验证 Authenticode 签名。
6. 验证至少以下故障路径：缺少模型包、模型包与基础包版本不匹配、CUDA 不可用回退 CPU、编码器不可用回退 CPU、磁盘空间预检失败、取消后 `--resume`。
7. 上传前检查 Release 说明、更新日志、安装说明和版本号；上传后比较 GitHub 返回的每个资产大小和 SHA-256 摘要。

没有真实、可验证的证书时，发布必须明确标记为**未签名开发版**，不得声称已经代码签名。
