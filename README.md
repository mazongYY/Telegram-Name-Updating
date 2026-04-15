---
title: Telegram Name Updating
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Telegram-Name-Updating

自动更新 Telegram 账户的第一名称 (First Name)，使其包含当前时间（时钟 Emoji 形式）。

## 功能特点

- 自动根据当前时间更新 Telegram 账户名称。
- 支持自定义前缀和后缀。
- 支持代理配置。
- 支持持久化会话，无需重复登录。

## 使用方法 (本地运行)

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 运行脚本进行初始化配置：
   ```bash
   python tg_username_update.py --init-config
   ```
3. 启动脚本：
   ```bash
   python tg_username_update.py
   ```

## 使用 Docker 运行

推荐使用 Docker，这样可以方便地在后台运行。

### 1. 构建镜像
```bash
docker build -t tg-username-update .
```

### 2. 初始化配置 (首次运行)
如果你还没有 `config.local.json`，可以先通过以下方式运行一次以生成配置：
```bash
docker run -it --name tg-update -v $(pwd):/app tg-username-update --init-config
```
之后根据提示输入 API ID、Hash、手机号等信息。

### 3. 使用 Docker Compose (推荐)
1. 确保目录下已有 `config.local.json` 和生成的 `.session` 文件（如果是首次，也可以在 compose 中启动）。
2. 启动容器：
   ```bash
   docker-compose up -d
   ```
3. 如果需要处理首次登录的验证码，可以 attach 到容器：
   ```bash
   docker attach tg-username-update
   ```

## GitHub Actions

本项目已配置 GitHub Actions 工作流，支持以下功能：
- **自动测试**：在代码推送或拉取请求时运行 Lint 检查。
- **自动构建并发布**：
  - 当代码推送到 `main` 或 `master` 分支时，自动构建 Docker 镜像并发布到 Docker Hub (`m3184876/telegram-name-updating`)。
  - 当发布新的 Tag (如 `v1.0.0`) 时，自动生成对应的版本镜像。

您可以从 Docker Hub 获取镜像：
```bash
docker pull m3184876/telegram-name-updating:latest
```

### 后续步骤
1. 请确保您在 GitHub 仓库的 **Settings > Secrets and variables > Actions** 中添加了以下两个 Repository secrets：
   - `DOCKERHUB_USERNAME`: 您的 Docker Hub 用户名 (`m3184876`)。
   - `DOCKERHUB_TOKEN`: 您的 Docker Hub 访问令牌 (Access Token)。
2. 将代码推送到 GitHub 的 `main` 或 `master` 分支，工作流将自动触发构建并发布。

### 注意事项
- 请确保 `config.local.json` 和 `.session` 文件在宿主机上，并通过挂载卷持久化，否则容器重启后需要重新登录。
- API ID 和 API Hash 可以从 [my.telegram.org](https://my.telegram.org) 获取。

## 在 Hugging Face Space 上如何登录 Telegram 账户

这个项目首次登录 Telegram 需要输入短信验证码，因此建议先在本地完成一次授权，再把会话文件同步到运行环境。

1. 在本地运行初始化：
   ```bash
   python tg_username_update.py --init-config
   ```
2. 本地启动一次主程序并按提示输入 Telegram 验证码（如果开启二步验证，也输入密码）：
   ```bash
   python tg_username_update.py
   ```
3. 成功后会生成会话文件（默认 `api_auth.session`），后续运行无需再次登录。
4. 部署到服务器 / 容器 / Space 时，确保 `config.local.json` 和 `api_auth.session` 能被持久化挂载，否则重启后会丢失登录状态。

