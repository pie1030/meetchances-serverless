#!/usr/bin/env bash
# 在 Linux 容器内验证 dist/meetchances-serverless.zip 可正常启动。
# 模拟函数运行时：只有代码包 + 环境变量注入的密钥，无 .venv、无 .env 文件。
#
#   ./verify_package.sh
#
# 需要 Docker。有本目录下的 .env 时会额外验证 POST /contact（会真写一条记录，
# 跑完请手动删除）；没有 .env 也能跑，只验证代码包能否在 Linux 上正常启动。
set -euo pipefail
cd "$(dirname "$0")"

ZIP=dist/meetchances-serverless.zip
test -f "$ZIP" || { echo "先执行 ./package.sh"; exit 1; }

# 容器架构必须与 package.sh 所用 wheel 一致，否则 .so 无法加载。
# package.sh 默认 x86_64-manylinux2014 → 这里对应 linux/amd64。
# 在 Apple Silicon 上会走 QEMU 模拟，启动较慢属正常。
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
# 刻意用非 8000 端口：若 run.sh 没读平台注入的 _BYTEFAAS_RUNTIME_PORT，
# 就会回落监听 8000，探活打不通 → 这个验证会失败。正是要暴露这种情况。
PORT_IN=9123
PORT_OUT=8097
NAME=meetchances-serverless-verify

# 保留容器供排查；仅在成功路径结束时清理
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
cleanup

ENV_ARGS=()
if [[ -f .env ]]; then
  ENV_ARGS=(--env-file .env)
  echo "→ 已发现 .env，将一并验证 POST /contact（会真写入表格）"
else
  echo "→ 无 .env，仅验证启动与 /health（POST /contact 预期 503）"
fi

echo "→ 在 python:3.12-slim（$DOCKER_PLATFORM）中解压代码包并以 ./run.sh 启动"
docker run -d --name "$NAME" \
  --platform "$DOCKER_PLATFORM" \
  -p "$PORT_OUT:$PORT_IN" \
  -e _BYTEFAAS_RUNTIME_PORT="$PORT_IN" \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} \
  -v "$PWD/$ZIP:/tmp/pkg.zip:ro" \
  python:3.12-slim \
  bash -c "mkdir -p /app && cd /app && python -c \"
import zipfile; zipfile.ZipFile('/tmp/pkg.zip').extractall('.')
\" && bash run.sh" >/dev/null

ready=0
for _ in $(seq 1 30); do
  sleep 2
  if curl -sf --noproxy '*' "http://127.0.0.1:$PORT_OUT/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
done

if [[ "$ready" != "1" ]]; then
  echo "❌ 服务未就绪，容器日志："
  docker logs "$NAME" 2>&1 | tail -20
  echo "（容器 $NAME 已保留，可用 docker logs 继续排查）"
  exit 1
fi

echo "→ GET /health"
curl -s --noproxy '*' "http://127.0.0.1:$PORT_OUT/health" -w "  HTTP %{http_code}\n"

echo "→ OPTIONS /contact（跨域预检，应带 access-control-allow-origin）"
curl -s --noproxy '*' -D - -o /dev/null -X OPTIONS "http://127.0.0.1:$PORT_OUT/contact" \
  -H "Origin: https://meetchances.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  | grep -i "access-control-allow-origin" || echo "  ❌ 预检未放行"

echo "→ OPTIONS /contact（未授权 Origin，应无 CORS 头）"
if curl -s --noproxy '*' -D - -o /dev/null -X OPTIONS "http://127.0.0.1:$PORT_OUT/contact" \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: POST" \
  | grep -qi "access-control-allow-origin"; then
  echo "  ❌ 未授权 Origin 被放行"
else
  echo "  OK  未授权 Origin 已拒绝"
fi

if [[ -f .env ]]; then
  echo "→ POST /contact（智能知识官网，完整；会真写一条）"
  curl -s --noproxy '*' -X POST "http://127.0.0.1:$PORT_OUT/contact" \
    -H "Content-Type: application/json" -H "Origin: http://human-intelligence.cn" \
    -d '{"name":"容器验证-勿删","job_title":"验证职位","company":"验证公司","contact":"docker@example.com","requirement":"验证 Linux 代码包"}' \
    -w "  HTTP %{http_code}\n"

  echo "→ POST /contact（缺必填，应 422）"
  curl -s --noproxy '*' -X POST "http://127.0.0.1:$PORT_OUT/contact" \
    -H "Content-Type: application/json" -H "Origin: http://human-intelligence.cn" \
    -d '{"name":"容器验证2","contact":"x@example.com"}' \
    -w "  HTTP %{http_code}\n"
else
  echo "→ POST /contact（无凭证，应 503）"
  curl -s --noproxy '*' -X POST "http://127.0.0.1:$PORT_OUT/contact" \
    -H "Content-Type: application/json" -H "Origin: https://meetchances.com" \
    -d '{"name":"x","company":"y","contact":"z","requirement":"w"}' \
    -w "  HTTP %{http_code}\n"
fi

echo ""
echo "→ 容器日志"
docker logs "$NAME" 2>&1 | tail -8

cleanup
echo ""
echo "✅ 代码包在 Linux 环境验证通过"
if [[ -f .env ]]; then
  echo "   注意：已往表格写入一条「容器验证-勿删」，请手动删除。"
fi
