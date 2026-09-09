# 部署到火山引擎 Web 应用函数

目标运行时：**Native Python 3.12 / x86_64**，通过 API 网关提供公网访问。

本仓库是多功能 Serverless 仓库，整个 `app/` 作为一个函数部署，所有模块共用一个
入口与一个网关地址。新增模块不需要改动本文档描述的流程。

## 一、打包

```bash
./package.sh          # 生成 dist/meetchances-serverless.zip
./verify_package.sh   # 在 linux/amd64 容器里跑一遍（需 Docker）
```

`verify_package.sh` 是上线前唯一能真正证明代码包可用的检查：它在 Linux 容器里
只用「代码包 + 环境变量」启动，没有 `.venv` 也没有 `.env`，并刻意用非 8000 端口
——若 `run.sh` 没读平台注入的 `_BYTEFAAS_RUNTIME_PORT`，探活就会失败。
有 `.env` 时会额外真写一条记录（跑完需手动删除），没有也能验证启动与 CORS。

包内结构对齐官方模版 `vefaas-native-python3.12-default`：

```
meetchances-serverless.zip
├── run.sh            # 入口：设 PYTHONPATH、绑 0.0.0.0、读平台注入端口
├── app/              # 业务代码（含 main.py、api/ 各模块）
├── requirements.txt  # 由 uv.lock 导出，仅运行时依赖
└── site-packages/    # vendored 依赖，函数运行时不执行 pip install
```

刻意**不含** `.env`、`tests/`、`__pycache__`：密钥通过控制台环境变量注入，不入代码包。

### 两种打包模式

```bash
./package.sh              # cross：在 Mac 上直接下目标平台 wheel，默认
MODE=docker ./package.sh  # 在 linux/amd64 容器内真实安装（需 Docker）
```

`cross` 模式用 `uv pip install --python-platform x86_64-manylinux2014 --only-binary :all:`，
保证绝不在本机编译 —— 本机编译必然产出 arm64 Mach-O，函数运行时会直接崩。
若某依赖只提供源码分发导致 cross 失败，改用 `MODE=docker`。

打包最后一步会**正面断言**每个扩展模块都是目标架构的 ELF（当前 7 个）。
只黑名单 `*darwin*.so` 是不够的：ARM Linux 的 `.so` 文件名里同样带 `linux`，
会蒙混过关并在 x86_64 运行时崩溃。

## 二、控制台配置

### 环境变量

| 变量 | 说明 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用凭证，开放平台 → 凭证与基础信息 |
| `FEISHU_APP_SECRET` | 同上。**只在控制台配置，不入代码包、不进 Git** |
| `FEISHU_APP_TOKEN` | 目标多维表格的 app_token |
| `FEISHU_TABLE_ID` | 目标数据表的 table_id |

`FEISHU_APP_TOKEN` / `FEISHU_TABLE_ID` 取值见表格 URL：
`/base/<FEISHU_APP_TOKEN>?table=<FEISHU_TABLE_ID>`。

可选 `FEISHU_BASE_URL`，仅私有化部署需要。

飞书侧前置条件：应用已开通多维表格读写权限、已发布版本，并被加为目标表格的
**可编辑**协作者。三者缺一都会在写入时报权限错误。

### 启动命令

```
./run.sh
```

端口不要写死。`run.sh` 按 `_BYTEFAAS_RUNTIME_PORT` → `PORT` → `8000` 取值，
第一个才是火山引擎实际注入的变量名。

## 三、部署后验证

```bash
BASE=https://<你的网关地址>

curl $BASE/health
# {"status":"ok"}

# 一面千识官网
curl -X POST $BASE/contact \
  -H "Content-Type: application/json" \
  -H "Origin: https://meetchances.com" \
  -d '{"name":"验证-勿删","company":"测试","contact":"t@example.com","requirement":"验证"}'
# {"ok":true,"record_id":"rec...","source":"一面千识官网"}

# 智能知识官网（多一个 job_title）
curl -X POST $BASE/contact \
  -H "Content-Type: application/json" \
  -H "Origin: https://human-intelligence.cn" \
  -d '{"name":"验证-勿删","job_title":"测试","company":"测试","contact":"t@example.com"}'
# {"ok":true,"record_id":"rec...","source":"智能知识官网"}
```

## 三、切换官网前端

新服务与旧服务的 `/contact` 请求与响应格式完全一致，前端只需把 BASE 换成新网关
地址，无需改字段。两个官网调同一个 URL，来源由后端读 `Origin` 判定。

上线顺序建议：先部署新函数并用上面的 curl 验证，再改前端地址，最后下线旧函数。
