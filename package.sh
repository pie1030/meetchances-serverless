#!/usr/bin/env bash
# 打包火山引擎 Web 应用函数代码包。目标运行时：Native Python 3.12 / x86_64。
#
#   ./package.sh               -> dist/meetchances-serverless.zip（默认 cross 模式）
#   MODE=docker ./package.sh   -> 在 linux/amd64 容器内安装依赖（兜底）
#
# 包内结构对齐官方模版 vefaas-native-python3.12-default：
#   run.sh / app/ / requirements.txt / site-packages/
#
# 依赖 vendored 进 site-packages，因为函数运行时不执行 pip install。
# requirements.txt 由 uv.lock 导出而非手工维护，避免与锁文件漂移。
# 刻意不含 .env 与 tests/：密钥通过控制台环境变量注入，不入代码包。
set -euo pipefail
cd "$(dirname "$0")"

BUILD_DIR=build
DIST=dist/meetchances-serverless.zip
VENDOR="$BUILD_DIR/site-packages"

rm -rf "$BUILD_DIR" "$DIST"
mkdir -p "$VENDOR" dist

# 1) 业务代码与入口（tests/ 与本地配置不入包）
#    app/ 是包目录，用 rsync 排除 __pycache__；无 rsync 时退回 cp + find 清理
cp run.sh "$BUILD_DIR/"
chmod +x "$BUILD_DIR/run.sh"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude='__pycache__' app "$BUILD_DIR/"
else
  cp -R app "$BUILD_DIR/"
fi

# 2) 从 uv.lock 导出运行时依赖清单（不含 dev、不含本项目自身）
#    --no-hashes：后面要按目标平台下 wheel，带哈希会与平台解析冲突
uv export --no-dev --no-hashes --no-emit-project -o "$BUILD_DIR/requirements.txt" -q

# 3) 依赖装进 site-packages/，由 run.sh 里的 PYTHONPATH 引入
#    关键：pydantic_core 等含编译扩展，必须显式拉 Linux 平台的 wheel，
#    否则在 macOS 上装出的 *-darwin.so 会让函数运行时直接崩。
#    PLATFORM 用 uv 的目标三元组命名（不是 pip 的 manylinux2014_x86_64）。
PLATFORM="${PLATFORM:-x86_64-manylinux2014}"
PYVER="${PYVER:-3.12}"
MODE="${MODE:-cross}"

# 目标架构由 PLATFORM 前缀推出，docker 平台与 ELF 校验共用同一份判断
case "$PLATFORM" in
  x86_64-*)  DOCKER_PLATFORM=linux/amd64; EXPECT_MACHINE=0x3e; EXPECT_NAME="x86-64" ;;
  aarch64-*) DOCKER_PLATFORM=linux/arm64; EXPECT_MACHINE=0xb7; EXPECT_NAME="aarch64" ;;
  *) echo "❌ 无法从 PLATFORM=$PLATFORM 推断目标架构"; exit 1 ;;
esac

if [[ "$MODE" == "docker" ]]; then
  # Docker 模式：在目标平台容器内真实安装，不依赖预编译 wheel。
  # 当某个依赖只提供源码分发（sdist）时，cross 模式会失败，用这个兜底。
  echo "  Docker 模式：在 python:$PYVER-slim（$DOCKER_PLATFORM）内安装依赖"
  docker run --rm --platform "$DOCKER_PLATFORM" \
    -v "$PWD/$BUILD_DIR/requirements.txt:/req.txt:ro" \
    -v "$PWD/$VENDOR:/out" \
    "python:$PYVER-slim" \
    pip install -q --no-compile -r /req.txt --target /out
else
  # cross 模式（默认）：在 macOS 上直接下载目标平台 wheel。
  #   --only-binary :all: 保证绝不在本机编译 —— 本机编译必然产出 arm64 Mach-O。
  #   若某依赖无对应 wheel，此处直接报错而非静默降级，改用 MODE=docker。
  #   uv 默认不写 .pyc，无需 pip 的 --no-compile。
  uv pip install -q -r "$BUILD_DIR/requirements.txt" --target "$VENDOR" \
    --python-platform "$PLATFORM" --python-version "$PYVER" --only-binary :all:
fi

# 4) 校验：包内每个扩展模块都必须是目标平台的 ELF
#    只黑名单 *darwin*.so 不够 —— ARM Linux 的 .so 文件名里同样带 "linux"，
#    会蒙混过关并在 x86_64 运行时崩溃。这里改成正面断言 ELF 架构。

python3 - "$VENDOR" "$EXPECT_MACHINE" "$EXPECT_NAME" <<'PY'
import pathlib
import sys

vendor = pathlib.Path(sys.argv[1])
expect, expect_name = int(sys.argv[2], 16), sys.argv[3]
MACHINES = {0x03: "i386", 0x28: "arm", 0x3E: "x86-64", 0xB7: "aarch64"}

bad: list[str] = []
checked = 0
for path in sorted(vendor.rglob("*")):
    if not path.is_file():
        continue
    if path.suffix not in {".so", ".pyd", ".dylib"} and ".so." not in path.name:
        continue
    rel = path.relative_to(vendor)
    head = path.open("rb").read(20)
    if head[:4] != b"\x7fELF":
        bad.append(f"{rel}：不是 ELF（Mach-O / Windows 二进制？）")
        continue
    machine = int.from_bytes(head[18:20], "little")
    if machine != expect:
        got = MACHINES.get(machine, hex(machine))
        bad.append(f"{rel}：架构为 {got}，期望 {expect_name}")
        continue
    checked += 1

if bad:
    print("❌ 扩展模块架构不符，函数运行时会崩溃：")
    for item in bad:
        print("   -", item)
    raise SystemExit(1)
print(f"  扩展模块校验通过：{checked} 个 ELF {expect_name}")
PY

# 5) 清理无用文件后打包（zip 根目录即代码包根目录）
#    bin/ 是 console script，shebang 写死了打包机的绝对路径，
#    在 Linux 上不可用；run.sh 用 python -m uvicorn，不依赖它们。
rm -rf "$VENDOR/bin"
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -prune -exec rm -rf {} + 2>/dev/null || true
(cd "$BUILD_DIR" && zip -qr "../$DIST" .)

echo "✅ 已生成 $DIST（$(du -h "$DIST" | cut -f1)）"
echo "   平台：$PLATFORM  Python：$PYVER"
echo "   启动命令：./run.sh"
