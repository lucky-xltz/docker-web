/**
 * Docker 管理面板服务端
 *
 * 单进程同时做两件事：
 *   1. 作为静态服务器托管 index.html
 *   2. 把 /api/* 反向代理到本机 docker.sock（Unix socket 手写 HTTP）
 *
 * API 路由将请求转发至 Docker Engine：
 *   GET    /                        -> index.html
 *   GET    /api/containers/json     -> Docker: GET  /containers/json
 *   POST   /api/containers/x/start  -> Docker: POST /containers/x/start
 *   DELETE /api/images/nginx:alpine -> Docker: DELETE /images/nginx:alpine
 *   ...
 */

// 优先查找系统级 socket，其次查找当前用户的 Docker Desktop socket。
function findSocket(): string | null {
  const candidates = [
    "/var/run/docker.sock",
    `${Bun.env.HOME}/.docker/run/docker.sock`,
    ...(Bun.env.DOCKER_HOST?.startsWith("unix://")
      ? [Bun.env.DOCKER_HOST.slice("unix://".length)]
      : []),
  ];
  for (const p of candidates) {
    try {
      // 注意：用 size >= 0 判断不可靠（Bun 对不存在文件也可能返回 0），必须用 exists()
      if (Bun.file(p).exists()) return p;
    } catch {
      // 不是可读文件，继续找
    }
  }
  return null;
}

const DOCKER_SOCKET = findSocket();
const PORT = Number(Bun.argv[2] ?? Bun.env.PORT ?? 9999);
const INDEX_HTML = import.meta.dir + "/index.html";
const MAX_BODY = 64 * 1024 * 1024; // 上传/响应上限 64MB（拉镜像时进度流可能较大）

/** 把 Docker 返回的 chunked 编码还原为普通字节 */
function decodeChunked(buf: Uint8Array): Uint8Array {
  const out: number[] = [];
  let i = 0;
  while (i < buf.length) {
    let j = buf.indexOf(0x0d, i); // '\r'
    if (j === -1) break;
    while (j < buf.length && buf[j + 1] !== 0x0a) {
      j = buf.indexOf(0x0d, j + 1);
      if (j === -1) break;
    }
    if (j === -1 || j + 1 >= buf.length) break;
    const line = new TextDecoder().decode(buf.subarray(i, j)).split(";")[0].trim();
    const size = parseInt(line, 16);
    if (!Number.isFinite(size) || size <= 0) break;
    out.push(...buf.subarray(j + 2, j + 2 + size));
    i = j + 2 + size + 2;
  }
  return new Uint8Array(out);
}

/** 解析 Docker 响应的状态行 + 响应头 */
function parseHead(raw: string) {
  const end = raw.indexOf("\r\n\r\n");
  const head = end === -1 ? raw : raw.slice(0, end);
  const lines = head.split("\r\n");
  const parts = lines[0].split(" ");
  const status = Number(parts[1]);
  const headers = new Map<string, string>();
  for (const line of lines.slice(1)) {
    const idx = line.indexOf(":");
    if (idx !== -1) headers.set(line.slice(0, idx).trim().toLowerCase(), line.slice(idx + 1).trim());
  }
  return { status, headers };
}

/** 查找 HTTP 头分隔符 \r\n\r\n 的位置，找不到返回 -1 */
function findHeadEnd(buf: Uint8Array): number {
  for (let i = 0; i + 3 < buf.length; i++) {
    if (buf[i] === 0x0d && buf[i + 1] === 0x0a && buf[i + 2] === 0x0d && buf[i + 3] === 0x0a) {
      return i;
    }
  }
  return -1;
}

const encoder = new TextEncoder();
const errText = (s: string, status = 502) =>
  new Response(s, { status, headers: { "content-type": "text/plain; charset=utf-8" } });

Bun.serve({
  port: PORT,
  // 必须监听 0.0.0.0：容器里 Docker 的端口转发连的是容器 eth0，
  // 绑 127.0.0.1 会被拒（表现为宿主机访问 Connection reset by peer）。
  hostname: Bun.env.HOST ?? "0.0.0.0",
  idleTimeout: 0, // 容器日志 / 镜像拉取可能长时间无数据，不主动断开
  async fetch(req) {
    const url = new URL(req.url);

    if (url.pathname === "/healthz") {
      return Response.json({
        ok: true,
        socket: DOCKER_SOCKET ?? null,
        uptime: Math.round(process.uptime()),
      });
    }

    if (url.pathname !== "/api" && !url.pathname.startsWith("/api/")) {
      const file = Bun.file(INDEX_HTML);
      if (!(await file.exists())) return errText("index.html 不存在\n", 500);
      return new Response(file, {
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-cache",
        },
      });
    }

    if (!DOCKER_SOCKET) {
      return errText("找不到 docker.sock（且未设置 DOCKER_HOST），请确认 Docker 已启动\n", 503);
    }

    // ---- /api/containers/json  ->  docker: GET /containers/json ----
    const dockerPath = url.pathname.slice(4) + url.search;

    // ---- 读取请求体 ----
    let body: Uint8Array | undefined;
    const lenHeader = req.headers.get("content-length");
    const len = req.body ? Number(lenHeader ?? (await req.arrayBuffer()).byteLength) : 0;
    if (len > MAX_BODY) return errText("请求体过大", 413);
    if (req.body) body = new Uint8Array(await req.arrayBuffer());

    // ---- 连接 docker.sock 并收发数据 ----
    // 注意：Bun.connect 一旦注册 data 回调，sock.readable 即为 undefined，
    // 必须用回调累积响应，不能在返回后从流里读。
    let chunks: Uint8Array[] = [];
    let total = 0;
    let settled: () => void;
    const finished = new Promise<void>((r) => {
      settled = r;
    });

    let sock: Awaited<ReturnType<typeof Bun.connect>>;
    try {
      sock = await Bun.connect({
        unix: DOCKER_SOCKET,
        socket: {
          data(_s, chunk) {
            total += chunk.length;
            if (total > MAX_BODY) {
              chunks = [];
              _s.end();
              return;
            }
            chunks.push(chunk);
          },
          error(_s, e) {
            console.error("[docker]", e);
          },
          close() {
            settled();
          },
        },
      });
    } catch (e) {
      return errText(
        `Cannot connect to docker: ${e}\n` +
          `(socket: ${DOCKER_SOCKET}，容器内可执行 ` +
          `docker exec <name> ls -l /var/run/docker.sock 确认属组，` +
          `必要时用 user "0:0" 或以 docker 组 gid 运行)`,
      );
    }

    const head =
      `${req.method} ${dockerPath} HTTP/1.1\r\n` +
      `Host: localhost\r\n` +
      `Connection: close\r\n` +
      `Content-Length: ${body?.length ?? 0}\r\n` +
      (req.headers.get("content-type") ? `Content-Type: ${req.headers.get("content-type")}\r\n` : "") +
      `\r\n`;
    sock.write(encoder.encode(head));
    if (body?.length) sock.write(body);

    // ---- 等待完整响应（HTTP/1.1 + Connection: close，EOF 即完整）----
    const timer = setTimeout(() => settled(), 120_000);
    try {
      await finished;
    } finally {
      clearTimeout(timer);
      sock.end();
    }

    const raw = concat(chunks);
    const headEnd = findHeadEnd(raw);
    if (headEnd === -1) return errText("Bad response from docker\n");

    const { status, headers } = parseHead(new TextDecoder("latin1").decode(raw.subarray(0, headEnd)));
    let respBody = raw.subarray(headEnd + 4);

    if ((headers.get("transfer-encoding") ?? "").toLowerCase().includes("chunked")) {
      respBody = decodeChunked(respBody);
    }

    const contentType = headers.get("content-type") ?? "application/json";
    const outHeaders: Record<string, string> = {
      "content-type": contentType,
      "content-length": String(respBody.length),
    };
    // 拉镜像接口是长连接流式进度，禁用缓冲让前端实时看到
    if (dockerPath.startsWith("/images/create")) outHeaders["cache-control"] = "no-cache";

    return new Response(respBody, { status, headers: outHeaders });
  },
});

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

if (!DOCKER_SOCKET) {
  console.warn("⚠️  未找到 docker.sock，API 调用会返回 503（静态页面仍可用）");
}
console.log(`docker.sock: ${DOCKER_SOCKET ?? "(未找到)"}`);
console.log(`面板地址:    http://localhost:${PORT}`);
