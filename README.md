# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威：** [magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

安装与 `magicdub update` **默认跟随 GitHub 最新正式 Release**（`/releases/latest`：已发布、非 draft、非 prerelease）。可用 `MAGICDUB_REF` 或 `magicdub update --ref` 覆盖为某 tag／分支／commit。

## 安装

macOS／Linux 一句安装（缺 uv／ffmpeg 时会尽量补齐；Python 由 uv 拉取；版本 = 最新正式 Release）：

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/install.sh | sh
```

装好后全局命令为 `magicdub`（通常在 `~/.local/bin`；若找不到，把该目录加入 `PATH`）。验证：`magicdub --version`。仓库／包名仍为 `magicdub-cli`。

安装、升级或任意 `magicdub` 命令会确保 **`~/.magicdub/cli/`** 下有 **`config.yaml`** 与 **`credentials`**：缺文件写完整默认；已有文件则**补齐缺失项**、保留你已填的值（凭据从不改写已有 Key）。请编辑 `credentials` 填入 Key：

```text
FAL_KEY=...
DEEPSEEK_API_KEY=...
```

指定版本示例：`MAGICDUB_REF=v0.1.1 sh install.sh`。

Windows：先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 与 ffmpeg，再执行（将 `<tag>` 换成 [Releases](https://github.com/shishengkai/magicdub-cli/releases) 上的最新正式 tag），然后任跑一次 `magicdub --version` 以生成配置文件：

```bash
uv tool install --force git+https://github.com/shishengkai/magicdub-cli.git@<tag>
magicdub --version
```

## 升级

日常升级到**最新正式 Release**（需已能运行 `magicdub`，且本机有 `uv`）：

```bash
magicdub update
```

指定 ref：

```bash
magicdub update --ref v0.1.1
```

`magicdub` 命令不可用、或想重装本工具时，再跑一遍安装脚本（救援／重装 magicdub-cli；**不会**把已有的 uv／ffmpeg 升到最新，只在缺失时才安装）：

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/install.sh | sh
```

一般不必先卸载。

## 卸载

三种程度递增（后一种包含前一种）：

1. **只卸工具和命令入口**（保留配置／凭据与任务目录）

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/uninstall.sh | sh
```

2. **再删凭据和配置**（`~/.magicdub/cli/`）

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/uninstall.sh | sh -s -- --purge
```

3. **再删默认任务目录**（如 macOS `~/Movies/MagicDub/cli/`；不可恢复）

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/uninstall.sh | sh -s -- --purge --purge-tasks
```

已 clone 时也可：`sh uninstall.sh`（同样可加 `--purge`／`--purge-tasks`）。

## 运行

```bash
magicdub run <video> --src en --tgt zh-Hans
```

每次 `run` 创建全新任务目录（默认 macOS：`~/Movies/MagicDub/cli/`）。v0.1.0 范围不做续跑。

## 开发

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest
```
