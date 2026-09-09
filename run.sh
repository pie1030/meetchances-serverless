#!/usr/bin/env bash
# 火山引擎 Web 应用函数入口，同时可用于本地启动。
#
#   ./run.sh                本地启动（默认 8000）
#   ./run.sh --port 9000    指定端口
#   ./run.sh --reload       本地开发热重载
#
# 结构与端口约定对齐官方模版 vefaas-native-python3.12-default：
# 平台注入 _BYTEFAAS_RUNTIME_PORT，依赖放 ./site-packages 由 PYTHONPATH 引入。
set -ex
cd "$(dirname "$0")"

# 平台侧代码包可能多一层 output/（与官方模版一致的兜底）
if [ -d "output" ]; then
  cd ./output/
fi

HOST="0.0.0.0"
# 端口优先级：平台注入 > 手动 PORT > 8000。
# _BYTEFAAS_RUNTIME_PORT 是火山引擎实际注入的变量名，不能只读 PORT。
PORT="${_BYTEFAAS_RUNTIME_PORT:-${PORT:-8000}}"

# 依赖 vendored 在 ./site-packages（函数运行时不执行 pip install）
export PYTHONPATH="$PYTHONPATH:./site-packages"

# 解析 --host/--port，其余参数（如 --reload）透传给 uvicorn
EXTRA=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --port)
      PORT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    *)
      EXTRA+=("$1")
      shift
      ;;
  esac
done

# 本地有 venv 时优先用它；函数运行时用镜像自带的 python3
PYTHON=python3
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
fi

exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" ${EXTRA[@]+"${EXTRA[@]}"}
