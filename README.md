# magicdub-cli

本地视频译制 CLI：编排式 pipeline + slot／adapter，产出配音成片、混音母版与 SRT。

**设计权威（brain）：**  
[magicdub-cli 系统设计](https://github.com/AaronJiTuo/magicdub-brain/blob/main/Releases/06_magicdub-cli系统设计.md)  
实现与验收以该文 **第 2 节（v0.1.0）** 为准。永远不做口型修正。

## 状态

空仓库，待按 Release 从 **M0** 开工。

## 计划依赖

- Python ≥ 3.12
- 系统：`ffmpeg`、`ffprobe`
- 凭据：`FAL_KEY`、`DEEPSEEK_API_KEY`（见 `~/.magicdub/credentials`）

## 目标入口（实现后）

```bash
uv tool install .
magicdub-cli run <video> --src en --tgt zh-Hans
```

每次 `run` 创建全新任务目录；v0.1.0 不做续跑。
