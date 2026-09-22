# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威：** [magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

## 安装

macOS／Linux 一句安装（缺 uv／ffmpeg 时脚本会尽量补齐；Python 由 uv 拉取）：

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/install.sh | sh
```

装好后全局命令为 `magicdub`（通常在 `~/.local/bin`；若找不到命令，把该目录加入 `PATH`）。验证：`magicdub --version`。仓库／包名仍为 `magicdub-cli`。

可选环境变量：`MAGICDUB_REF`（默认 `main`，也可设为 tag／commit）。Windows 请先自行安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 与 ffmpeg，再执行：

```bash
uv tool install --force git+https://github.com/shishengkai/magicdub-cli.git@main
```

凭据写入 `~/.magicdub/cli/credentials`（优先）；文件里没有的 key 再读环境变量。与 `magicdub-skills` 的凭据文件分开，不读 `~/.magicdub/credentials`／`credentials.env`。

```text
FAL_KEY=...
DEEPSEEK_API_KEY=...
```

可选配置：同目录 `~/.magicdub/cli/config.yaml`。

## 运行

```bash
magicdub run <video> --src en --tgt zh-Hans
```

每次 `run` 创建全新任务目录（默认 macOS：`~/Movies/MagicDub/cli/`）。v0.1.0 不做续跑。

## 开发

```bash
uv sync --extra dev   # 若已配置；或: uv pip install -e ".[dev]"
uv run ruff check src tests
uv run pytest
```
