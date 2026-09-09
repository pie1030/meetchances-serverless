# meetchances-serverless

MeetChances 的 Serverless 后端服务仓库，独立于 `meetchances-platform`。

这里承载相对独立、适合部署到 Serverless 的轻量后端能力，例如官网接口、飞书机器人、飞书多维表格读写、AI 相关接口等。每类能力作为 `app/api/` 下的一个模块存在，互不耦合。

当前处于第一阶段：基础 FastAPI 骨架 + 健康检查接口。

## 环境要求

- Python 3.12（已在 `.python-version` 中固定）
- [uv](https://docs.astral.sh/uv/)（用于管理虚拟环境和依赖）

无需手动创建虚拟环境，`uv` 会按 `.python-version` 自动准备 `.venv`。

## 安装 / 同步依赖

```bash
uv sync
```

该命令会创建 `.venv` 并按 `uv.lock` 安装全部依赖（含开发依赖）。仅需运行时依赖时：

```bash
uv sync --no-dev
```

## 启动本地服务

```bash
uv run uvicorn app.main:app --reload
```

默认监听 `http://127.0.0.1:8000`，`--reload` 会在代码变更后自动重启。

## 访问 /health

```bash
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status": "ok"}
```

交互式接口文档：`http://127.0.0.1:8000/docs`

## 运行测试

```bash
uv run pytest
```

## 目录结构

```
meetchances-serverless/
├── app/
│   ├── main.py                  # 创建 FastAPI app，注册聚合路由
│   └── api/
│       ├── router.py            # 聚合路由：所有业务模块在此挂载
│       ├── health/              # 健康检查模块
│       │   ├── router.py        # GET /health
│       │   ├── service.py       # 健康状态逻辑
│       │   └── schemas.py       # 响应模型
│       └── website/             # 官网模块（预留，暂无接口）
│           └── router.py
├── tests/
│   └── test_health.py
├── pyproject.toml               # 项目元信息与依赖声明
├── uv.lock                      # 依赖锁定文件（需提交）
├── .python-version              # 固定 Python 版本
└── .gitignore
```

各层职责：

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | 只负责创建 app 和注册 `api_router`，不包含任何业务路由 |
| `app/api/router.py` | 唯一的路由注册点，新增模块只需在此 `include_router` 一行 |
| `<module>/router.py` | HTTP 层：处理路径、入参校验、响应模型，不写业务逻辑 |
| `<module>/service.py` | 业务层：纯逻辑，不依赖 FastAPI，便于单测和跨模块复用 |
| `<module>/schemas.py` | 契约层：Pydantic 请求/响应模型 |

## 新增一个业务模块

以飞书机器人为例：

1. 建立 `app/api/feishu/`，按需添加 `router.py`、`service.py`、`schemas.py`
2. 在 `router.py` 中声明带前缀的 router：`APIRouter(prefix="/feishu", tags=["feishu"])`
3. 在 `app/api/router.py` 中挂载它

无需修改 `app/main.py`。

## 约定

- 不提交 `.venv`、`.env` 及任何密钥文件
- 需要环境变量时，新增 `.env.example` 说明所需变量，真实值只放在本地 `.env`（已被 git 忽略）
- `uv.lock` 需要提交，以保证环境一致
