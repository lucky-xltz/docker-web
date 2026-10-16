FROM oven/bun:1-alpine

WORKDIR /app

# 只拷贝运行所需文件，无依赖安装（零 npm 包）
COPY --chown=bun:bun package.json ./
COPY --chown=bun:bun src/index.html ./src/
COPY --chown=bun:bun src/server.ts ./src/

ENV NODE_ENV=production
ENV PORT=9999

EXPOSE 9999

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD bun -e "fetch('http://127.0.0.1:9999/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# 默认 root，保证能访问挂载进来的 docker.sock（通常是 srw-rw---- root:root）。
# 想更安全可改为非 root，但需让容器 gid 匹配宿主机 docker.sock 属组。
CMD ["bun", "run", "src/server.ts"]
