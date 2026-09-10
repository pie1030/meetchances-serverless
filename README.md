# meetchances-serverless

MeetChances 的通用 Serverless 后端仓库。

## 项目简介

这里放相对独立、体量不大、适合按请求计费的后端能力：官网接口、飞书机器人、飞书多维
表格读写、Webhook 回调等。这类服务各自都不值得单独开一个仓库和一条部署流水线，放在
一起共用同一份依赖、同一个函数、同一个网关地址。

整个 `app/` 作为**一个**火山引擎 Web 应用函数部署，内部按模块划分路由。新增一项能力
等于新增一个模块目录，不需要新建函数，也不需要改部署流程。

现有模块：

| 模块 | 接口 | 说明 |
| --- | --- | --- |
| `health` | `GET /health` | 存活探针，部署后第一件事就是打它 |
| `website` | `POST /contact` | 两个官网的「联系我们」表单：写入飞书多维表格，并往飞书群发通知卡片 |

## 项目结构

```
meetchances-serverless/
├── app/
│   ├── main.py                  # 创建 FastAPI app，注册聚合路由与 CORS
│   ├── feishu.py                # 飞书多维表格客户端（跨模块共享）
│   ├── feishu_bot.py            # 群机器人 Webhook 客户端（跨模块共享）
│   └── api/
│       ├── router.py            # 聚合路由：所有业务模块在此挂载
│       ├── health/              # 健康检查模块
│       │   ├── router.py        # GET /health
│       │   ├── service.py       # 健康状态逻辑
│       │   └── schemas.py       # 响应模型
│       └── website/             # 官网模块
│           ├── router.py        # POST /contact
│           ├── service.py       # 来源判定、必填校验、字段映射
│           ├── card.py          # 群通知卡片渲染
│           ├── schemas.py       # 请求/响应模型
│           └── sites.py         # 官网注册表：CORS 白名单与来源映射的唯一来源
├── tests/                       # 见「测试」一节
├── run.sh                       # 火山引擎入口，兼作本地启动
├── package.sh                   # 打包函数代码包
├── verify_package.sh            # 在 linux/amd64 容器里验证代码包
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
| `app/main.py` | 只创建 app、注册 `api_router` 与 CORS，不含任何业务路由 |
| `app/feishu.py` | 多维表格读写；用应用凭证，缓存 `tenant_access_token`。表格列名归各模块自己管 |
| `app/feishu_bot.py` | 群机器人 Webhook；只管把卡片发出去，不管卡片长什么样 |
| `app/api/router.py` | 唯一的路由注册点，新增模块只需在此 `include_router` 一行 |
| `<module>/router.py` | HTTP 层：路径、入参校验、响应模型，不写业务逻辑 |
| `<module>/service.py` | 业务层：纯逻辑，不依赖 FastAPI，便于单测和跨模块复用 |
| `<module>/schemas.py` | 契约层：Pydantic 请求/响应模型 |

## 本地开发

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                            # 创建 .venv 并按 uv.lock 装全部依赖
cp .env.example .env               # 然后填入真实值
uv run uvicorn app.main:app --reload
```

默认监听 `http://127.0.0.1:8000`。确认起来了：

```bash
curl http://127.0.0.1:8000/health   # {"status":"ok"}
```

交互式接口文档在 `http://127.0.0.1:8000/docs`。

也可以用部署入口启动，行为与函数运行时一致：

```bash
./run.sh                # 8000
./run.sh --port 9000
./run.sh --reload
```

只装运行时依赖用 `uv sync --no-dev`。

## 环境变量

本地放在 `.env`，线上在函数控制台注入。**`.env` 已被 git 忽略，切勿提交**；
`.env.example` 里只有变量名和占位值，真实凭证不进仓库。

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `FEISHU_APP_ID` | 是 | 飞书应用凭证，开放平台 → 凭证与基础信息 |
| `FEISHU_APP_SECRET` | 是 | 同上 |
| `FEISHU_APP_TOKEN` | 是 | 目标多维表格的 app_token，取自表格 URL 的 `/base/<app_token>` |
| `FEISHU_TABLE_ID` | 是 | 目标数据表的 table_id，取自同一 URL 的 `?table=` |
| `FEISHU_BOT_WEBHOOK_URL` | 否 | 通知群的自定义机器人 Webhook。不配就不发群通知，表单照常写入 |
| `FEISHU_BOT_WEBHOOK_SECRET` | 否 | 仅当机器人开了签名校验时才配。没开却配上，请求会被拒收 |
| `FEISHU_BITABLE_VIEW_URL` | 否 | 卡片「查看记录」按钮的跳转地址，填表格视图 URL 原样即可。不配就不显示按钮 |
| `FEISHU_BASE_URL` | 否 | 飞书开放平台域名，默认 `https://open.feishu.cn`，仅私有化部署需要 |

Webhook 地址等同凭证——谁拿到都能往群里发消息——按密钥对待。

四个必需变量缺任意一个时，`/health` 照常可用，`POST /contact` 返回
`503 服务暂不可用`。

飞书侧前置条件：应用已开通多维表格读写权限、已发布版本，并被加为目标表格的**可编辑**
协作者。三者缺一都会在写入时报权限错误。

## API

### GET /health

存活探针。无参数，恒返回 `{"status": "ok"}`，不依赖任何环境变量或外部服务，所以它能
答就说明进程起来了、路由挂上了。

### POST /contact

两个官网的「联系我们」表单都提交到这一个接口。**来源网站由后端读 `Origin` 判定，不接受
前端传值**，所以两站共用一个 URL，前端也无法伪造来源。

请求体字段（首尾空白会被去掉，纯空白等同未填）：

| 字段 | 类型 | 智能知识官网 | 一面千识官网 | 上限 |
| --- | --- | --- | --- | --- |
| `name` | string | 必填 | 必填 | 100 |
| `job_title` | string | 必填 | 无此字段 | 100 |
| `company` | string | 必填 | 必填 | 200 |
| `contact` | string | 必填 | 必填 | 200 |
| `requirement` | string | 可选 | 必填 | 5000 |

响应：

| 状态码 | body | 含义 |
| --- | --- | --- |
| `200` | `{"ok":true,"record_id":"rec...","source":"..."}` | 写入成功 |
| `422` | `{"detail":"缺少必填项：职位、公司"}` | `detail` 是中文，可直接展示 |
| `502` | `{"detail":"提交失败，请稍后重试"}` | 飞书接口异常 |
| `503` | `{"detail":"服务暂不可用"}` | 飞书环境变量未配置 |
| `504` | `{"detail":"提交超时，请稍后重试"}` | 网络超时 |

字段超长走的是 Pydantic 默认的 422，`detail` 为**数组**而非字符串，前端直接渲染会显示
`[object Object]`，取值前先判类型：

```js
const msg = typeof data.detail === 'string' ? data.detail : '提交失败，请稍后重试'
```

来源判定与 CORS 白名单：

| Origin | 写入「来源网站」列 |
| --- | --- |
| `human-intelligence.cn`、`www.` 前缀（http + https） | 智能知识官网 |
| `human-intelligence.xpertiise.com`（仅 https） | 智能知识官网（测试） |
| `meetchances.com`、`www.` 前缀（http + https） | 一面千识官网 |
| `testwebsite.meetchances.com`（仅 https） | 一面千识官网（测试） |
| `localhost:5173`、`localhost:3000` | 未知来源（放行跨域，但不冒充真实线索） |
| 其他 / 不带 Origin | 未知来源（并打 warning 日志） |

测试站用带「（测试）」的独立取值，便于在表格里筛掉测试数据；必填规则与对应正式站共用
同一个元组，不会漂移。白名单与来源映射都从
[app/api/website/sites.py](app/api/website/sites.py) 的 `SITES` 派生，**加域名只改这一
处**。不使用 `allow_origins=["*"]`：本接口写入共享表格，白名单是必要的。

写入飞书的列：

| 请求字段 | 表格列 | 说明 |
| --- | --- | --- |
| `name` | 姓名 | 表格索引列 |
| `job_title` | 职位 | 一面千识官网不传，留空即不写该列 |
| `company` | 公司 | |
| `contact` | 联系方式 | |
| `requirement` | 需求说明 | |
| —（后端判定） | 来源网站 | 由 `Origin` 推出 |
| —（后端生成） | 提交时间 | 毫秒时间戳，北京时间 |

「提交时间」必须是普通 DateTime 列：飞书不会自动填，得由后端写；一旦在表格里把它改成
「创建时间」类型就变成只读，每次写入都会被拒绝。`tests/test_feishu_live.py` 守着这条。

写入成功后往飞书群发一张卡片：标题「官网新联络意向」，副标题是来源网站，正文按 姓名 /
职位 / 公司 / 联系方式 / 需求说明 逐行显示（未填的行不显示），页脚是提交时间，末尾一个
「查看记录」按钮跳到表格里的那一行。正式站蓝色标题，测试站与未知来源灰色。发送放在
FastAPI 后台任务里：响应先返回给前端，多一次飞书调用不拖慢提交；发送失败只记日志，
`POST /contact` 仍返回 200 —— 记录已经写进表格了。

## 测试

```bash
uv run pytest
```

默认全程 stub 掉飞书客户端与群机器人：不发网络请求、不需要凭证、不写共享表格，所以在
没配 `.env` 的机器上也能跑。

| 文件 | 覆盖 |
| --- | --- |
| `tests/conftest.py` | 共享 fixture，stub 掉飞书客户端与群机器人 |
| `tests/test_health.py` | `GET /health` |
| `tests/test_contact.py` | `POST /contact` 的校验、字段映射、错误处理 |
| `tests/test_cors.py` | 跨域放行与站点注册表守卫 |
| `tests/test_notify.py` | 群通知卡片的内容与发送时机 |
| `tests/test_feishu_live.py` | 真连飞书的字段自检（默认跳过） |

真连飞书的两档，需要 `.env`：

```bash
# 只读，核对表格列名与类型
RUN_LIVE_FEISHU=1 uv run pytest tests/test_feishu_live.py -v

# 真写入一条（跑完请手动删除）
RUN_LIVE_FEISHU=1 FEISHU_LIVE_WRITE=1 uv run pytest tests/test_feishu_live.py -v
```

## 开发规范

- 注释、docstring、`/docs` 里的 `summary` 统一用中文，与仓库现状保持一致。
- 注释写「为什么这么做」，不写「这行在干什么」。
- 新模块一律带路径前缀，例如 `APIRouter(prefix="/feishu", tags=["feishu"])`。
  `website` 模块的 `/contact` 是唯一例外 —— 两个官网线上已经在往这个绝对路径提交。
- 不提交 `.venv`、`.env` 及任何密钥文件。新增环境变量时同步更新 `.env.example`，
  里面只放变量名和占位值。
- `uv.lock` 需要提交，以保证本地与函数运行时依赖一致。
- 敏感信息不进日志。凭证类错误只记变量名，不记值。

写飞书卡片时有几个坑，都踩过一次：

- 卡片 JSON 2.0 里普通文本组件是 `div` + 嵌套 `text`，**没有** `plain_text` 组件。
  直接拿 `{"tag": "plain_text"}` 当元素用，整张卡片会被拒收（错误码 `200621`）。
- `schema` 必须显式声明 `"2.0"`，否则按 1.0 解析。
- 只有在机器人「安全设置」里开了签名校验才该带 `timestamp`/`sign`，没开却带上会被
  拒收。被签名的是**空字符串**，密钥是 `timestamp\nsecret`。

## 部署

部署到火山引擎 Web 应用函数（Native Python 3.12 / x86_64），通过 API 网关暴露公网访问：

```bash
./package.sh          # 生成 dist/meetchances-serverless.zip
./verify_package.sh   # 在 linux/amd64 容器里跑一遍（需 Docker）
```

上传代码包、把启动命令设为 `./run.sh`、在控制台注入上面那张表里的环境变量。打包模式、
端口注入、部署后验证的完整说明见 [DEPLOY.md](DEPLOY.md)。

## 后续扩展

新增一项能力就是新增一个模块目录，以飞书机器人为例：

1. 建 `app/api/feishu/`，按需添加 `router.py`、`service.py`、`schemas.py`
2. 在 `router.py` 里声明带前缀的 router：`APIRouter(prefix="/feishu", tags=["feishu"])`
3. 在 `app/api/router.py` 中 `include_router` 挂上

不需要改 `app/main.py`，也不需要新建函数或改部署流程。

跨模块复用的基础设施（飞书客户端这类）放 `app/` 根下，只服务单个模块的逻辑留在模块目录
内。目录按实际需要添加，不预先铺空壳。



