# meetchances-serverless

MeetChances 的 Serverless 后端服务仓库。

这里承载相对独立、适合部署到 Serverless 的轻量后端能力，例如官网接口、飞书机器人、飞书多维表格读写、AI 相关接口等。
现有模块：

| 模块 | 接口 |
| --- | --- |
| `health` | `GET /health` |
| `website` | `POST /contact` |

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)（用于管理虚拟环境和依赖）


## 安装 / 同步依赖

```bash
uv sync
```

该命令会创建 `.venv` 并按 `uv.lock` 安装全部依赖。仅需运行时依赖时：

```bash
uv sync --no-dev
```

## 配置环境变量

`POST /contact` 需要飞书凭证。本地开发：

```bash
cp .env.example .env   # 然后填入真实值
```

`.env` 已被 git 忽略，**切勿提交**。部署环境不要上传 `.env`，改在函数控制台注入
环境变量（见 [DEPLOY.md](DEPLOY.md)）。

未配置时 `/health` 照常可用，`POST /contact` 返回 `503 服务暂不可用`。

## 启动本地服务

```bash
uv run uvicorn app.main:app --reload
```

默认监听 `http://127.0.0.1:8000`，`--reload` 会在代码变更后自动重启。

也可以用部署入口启动，行为与函数运行时一致：

```bash
./run.sh                # 8000
./run.sh --port 9000
./run.sh --reload
```

## 访问 /health

```bash
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status": "ok"}
```

交互式接口文档：`http://127.0.0.1:8000/docs`

## POST /contact

两个官网的「联系我们」表单都提交到这一个接口。**来源网站由后端读 `Origin`
判定，不接受前端传值**，所以两站共用一个 URL，前端也无法伪造来源。

| 字段 | 类型 | 智能知识官网 | 一面千识官网 | 上限 |
| --- | --- | --- | --- | --- |
| `name` | string | 必填 | 必填 | 100 |
| `job_title` | string | 必填 | 无此字段 | 100 |
| `company` | string | 必填 | 必填 | 200 |
| `contact` | string | 必填 | 必填 | 200 |
| `requirement` | string | 可选 | 必填 | 5000 |

首尾空白会被去掉，纯空白等同未填。

响应：

| 状态码 | body | 含义 |
| --- | --- | --- |
| `200` | `{"ok":true,"record_id":"rec...","source":"..."}` | 写入成功 |
| `422` | `{"detail":"缺少必填项：职位、公司"}` | `detail` 是中文，可直接展示 |
| `502` | `{"detail":"提交失败，请稍后重试"}` | 飞书接口异常 |
| `503` | `{"detail":"服务暂不可用"}` | 飞书环境变量未配置 |
| `504` | `{"detail":"提交超时，请稍后重试"}` | 网络超时 |

超长字段返回的是 Pydantic 默认的 422，`detail` 为**数组**而非字符串，前端直接
渲染会显示 `[object Object]`。前端应先判断类型，例如：

```js
const msg = typeof data.detail === 'string' ? data.detail : '提交失败，请稍后重试'
```

### 调用示例

```js
const BASE = 'https://<网关地址>'

const resp = await fetch(`${BASE}/contact`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  // 智能知识官网多传 job_title；一面千识官网不传这个字段
  body: JSON.stringify({ name, job_title, company, contact, requirement }),
})

const data = await resp.json()
if (!resp.ok) {
  showError(typeof data.detail === 'string' ? data.detail : '提交失败，请稍后重试')
}
```

### 来源判定与 CORS

| Origin | 写入「来源网站」列 |
| --- | --- |
| `human-intelligence.cn`、`www.` 前缀（http + https） | 智能知识官网 |
| `human-intelligence.xpertiise.com`（仅 https） | 智能知识官网（测试） |
| `meetchances.com`、`www.` 前缀（http + https） | 一面千识官网 |
| `testwebsite.meetchances.com`（仅 https） | 一面千识官网（测试） |
| `localhost:5173`、`localhost:3000` | 未知来源（放行跨域但不伪装成真实线索） |
| 其他 / 不带 Origin | 未知来源（并打 warning 日志） |

测试环境用带「（测试）」的独立取值，便于在表格里筛掉测试数据；必填规则与对应正式
站共用同一个元组，不会漂移。

CORS 白名单与来源映射都从 [app/api/website/sites.py](app/api/website/sites.py) 的
`SITES` 派生，**加域名只改这一处**。

不使用 `allow_origins=["*"]`：本接口写入共享表格，白名单是必要的。

### 飞书字段映射

| 请求字段 | 表格列 | 说明 |
| --- | --- | --- |
| `name` | 姓名 | 表格索引列 |
| `job_title` | 职位 | 一面千识官网不传，留空即不写该列 |
| `company` | 公司 | |
| `contact` | 联系方式 | |
| `requirement` | 需求说明 | |
| —（后端判定） | 来源网站 | 由 `Origin` 推出 |
| —（后端生成） | 提交时间 | 毫秒时间戳，北京时间 |

可选项为空时省略该键，不写空字符串。

表格**没有「编号」列**：飞书没有自动编号字段类型，记录靠 `record_id` 标识。
「提交时间」是普通 DateTime 列，飞书不会自动填，必须由后端写入——如果把它改成
「创建时间」类型就会变成只读，每次写入都会被拒绝。这两点由
`tests/test_feishu_live.py` 守着。

## 运行测试

```bash
uv run pytest
```

默认全程 stub 掉飞书客户端：不发网络请求、不需要凭证、不写共享表格。

对着真实表格核对字段（只读）：

```bash
RUN_LIVE_FEISHU=1 uv run pytest tests/test_feishu_live.py -v
```

真写入一条（跑完请手动删除）：

```bash
RUN_LIVE_FEISHU=1 FEISHU_LIVE_WRITE=1 uv run pytest tests/test_feishu_live.py -v
```

## 部署

见 [DEPLOY.md](DEPLOY.md)。

## 目录结构

```
meetchances-serverless/
├── app/
│   ├── main.py                  # 创建 FastAPI app，注册聚合路由与 CORS
│   ├── feishu.py                # 飞书多维表格客户端（跨模块共享的基础设施）
│   └── api/
│       ├── router.py            # 聚合路由：所有业务模块在此挂载
│       ├── health/              # 健康检查模块
│       │   ├── router.py        # GET /health
│       │   ├── service.py       # 健康状态逻辑
│       │   └── schemas.py       # 响应模型
│       └── website/             # 官网模块
│           ├── router.py        # POST /contact
│           ├── service.py       # 来源判定、必填校验、字段映射
│           ├── schemas.py       # 请求/响应模型
│           └── sites.py         # 官网注册表：CORS 白名单与来源映射的唯一来源
├── tests/
│   ├── conftest.py              # 共享 fixture，stub 掉飞书客户端
│   ├── test_health.py
│   ├── test_contact.py          # POST /contact 的校验、映射、错误处理
│   ├── test_cors.py             # 跨域与站点注册表守卫
│   └── test_feishu_live.py      # 真连飞书的字段自检（默认跳过）
├── run.sh                       # 火山引擎入口，兼作本地启动
├── package.sh                   # 打包函数代码包
├── DEPLOY.md                    # 部署说明
├── .env.example                 # 需要哪些环境变量
├── pyproject.toml               # 项目元信息与依赖声明
├── uv.lock                      # 依赖锁定文件（需提交）
├── .python-version              # 固定 Python 版本
└── .gitignore
```

各层职责：

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | 只负责创建 app、注册 `api_router` 与 CORS，不包含任何业务路由 |
| `app/feishu.py` | 跨模块共享的飞书客户端；表格专属的字段名归各模块自己管 |
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

新模块一律带路径前缀。`website` 模块的 `/contact` 是唯一例外 —— 两个官网线上已经
在往这个绝对路径提交，保留它才能不改前端直接替换旧服务。

## 约定

- 不提交 `.venv`、`.env` 及任何密钥文件
- 需要环境变量时，新增 `.env.example` 说明所需变量，真实值只放在本地 `.env`（已被 git 忽略）
- `uv.lock` 需要提交，以保证环境一致
