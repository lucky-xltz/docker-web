# docker-web

轻量级 Docker 管理面板，支持容器、Compose 项目、镜像和数据卷管理。

## 快速开始

需要 Docker Compose：

```bash
git clone https://github.com/lucky-xltz/docker-web.git
cd docker-web
docker compose up -d --build
```

打开 http://localhost:9999。面板通过挂载的 Docker socket 管理宿主机 Docker。

## 功能

- 容器状态静默同步与可配置刷新间隔
- Compose 项目分组、批量操作和项目日志
- 搜索容器、镜像和数据卷
- 镜像、数据卷管理，暗色 / 浅色主题

## 技术栈

Bun、原生 HTML/CSS/JavaScript、Docker Engine API。
