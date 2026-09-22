# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威：** [magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

## 安装

macOS／Linux 推荐用仓库内 `install.sh`（缺 uv／ffmpeg 时会尽量补齐；Python 由 uv 拉取）。

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

## 卸载

只卸命令（保留配置／凭据／任务成片）：

```bash
# 已 clone 时：
sh uninstall.sh

# 或已登录 gh（private 仓）：
gh api repos/shishengkai/magicdub-cli/contents/uninstall.sh -H "Accept: application/vnd.github.raw" | sh
```

等价于 `uv tool uninstall magicdub-cli`，并清理 `magicdub`／旧名 `magicdub-cli` 入口。

升级前也可先卸载再跑 `install.sh`。若连配置一起删：`sh uninstall.sh --purge`（删除 `~/.magicdub/cli`）。任务目录默认保留；要删默认任务父目录再加 `--purge-tasks`（不可恢复）。

公开后也可用：`curl -fsSL https://raw.githubusercontent.com/shishengkai/magicdub-cli/main/uninstall.sh | sh`

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
