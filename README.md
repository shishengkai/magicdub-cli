# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威：** [magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

## 安装

需要：Python ≥ 3.12、系统 `ffmpeg`／`ffprobe`、[uv](https://github.com/astral-sh/uv)。

```bash
uv tool install .
magicdub-cli --version
```

凭据写入 `~/.magicdub/credentials`（或环境变量）：

```text
FAL_KEY=...
DEEPSEEK_API_KEY=...
```

可选配置：`~/.magicdub/cli/config.yaml`。

## 运行

```bash
magicdub-cli run <video> --src en --tgt zh-Hans
```

每次 `run` 创建全新任务目录（默认 macOS：`~/Movies/MagicDub/cli/`）。v0.1.0 不做续跑。

## 开发

```bash
uv sync --extra dev   # 若已配置；或: uv pip install -e ".[dev]"
uv run ruff check src tests
uv run pytest
```
