# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威：** [magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

## 安装

macOS／Linux 推荐用仓库内 `install.sh`（缺 uv／ffmpeg 时会尽量补齐；Python 由 uv 拉取）。同一脚本也可用于**升级**和**救援**（命令坏了／旧入口 `magicdub-cli` 残留时重装）。

仓库公开后可用一句：

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/install.sh | sh
```

当前若仍是 **private**，匿名 raw 链不可用，改用（需已能访问该仓）：

```bash
git clone https://github.com/shishengkai/magicdub-cli.git
cd magicdub-cli && sh install.sh
```

或已登录 [GitHub CLI](https://cli.github.com/) 时：

```bash
gh api repos/shishengkai/magicdub-cli/contents/install.sh -H "Accept: application/vnd.github.raw" | sh
```

装好后全局命令为 `magicdub`（通常在 `~/.local/bin`；若找不到命令，把该目录加入 `PATH`）。验证：`magicdub --version`。仓库／包名仍为 `magicdub-cli`。

可选环境变量：`MAGICDUB_REF`（默认 `main`，也可设为 tag／commit）、`MAGICDUB_REPO_URL`。Windows 请先自行安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 与 ffmpeg，再执行：

```bash
uv tool install --force git+https://github.com/shishengkai/magicdub-cli.git@main
```

凭据写入 `~/.magicdub/cli/credentials`（优先）；文件里没有的 key 再读环境变量。与 `magicdub-skills` 的凭据文件分开，不读 `~/.magicdub/credentials`／`credentials.env`。

```text
FAL_KEY=...
DEEPSEEK_API_KEY=...
```

可选配置：同目录 `~/.magicdub/cli/config.yaml`。

## 升级

日常升级（需已能运行 `magicdub`，且本机有 `uv`）：

```bash
magicdub update
```

指定 ref（tag／分支／commit）：

```bash
magicdub update --ref main
```

`magicdub` 不可用、或想连同 uv／ffmpeg 一起检查时，再跑一遍 **`install.sh`**（升级／救援，不必先写 `update.sh`）。一般**不必**先 `uninstall`；只有要换掉残留旧入口或彻底重来时才卸载。

## 卸载

在已 clone 的仓库目录下执行（下面三种程度递增；后一种包含前一种）。

1. **只卸工具和命令入口**（保留 `~/.magicdub/cli` 配置／凭据，以及任务成片目录）

```bash
sh uninstall.sh
```

2. **在 1 的基础上，再删凭据和配置**（删除整个 `~/.magicdub/cli/`）

```bash
sh uninstall.sh --purge
```

3. **在 2 的基础上，再删默认任务目录**（如 macOS `~/Movies/MagicDub/cli/`；不可恢复）

```bash
sh uninstall.sh --purge --purge-tasks
```

未 clone、且已登录 [GitHub CLI](https://cli.github.com/) 时（private 仓），把脚本接到管道并带上同样参数，例如第 3 种：

```bash
gh api repos/shishengkai/magicdub-cli/contents/uninstall.sh \
  -H "Accept: application/vnd.github.raw" | sh -s -- --purge --purge-tasks
```

仓库公开后也可用：

```bash
curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/uninstall.sh | sh -s -- --purge
```

（无额外参数时去掉 `--` 后面的选项即可。）

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
