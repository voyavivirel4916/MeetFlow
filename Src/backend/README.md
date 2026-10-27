# MeetFlow 后端工程

T05已建立应用工厂、配置、启动检查、统一响应/错误和请求日志。运行基准为Windows、Python 3.11.9，依赖版本与哈希锁定在`requirements.txt`及`requirements-dev.txt`。

T07建立账户、会话、小组和成员四张基础表及显式Alembic迁移。T09认证、T10登录页面、T12小组接口和T13小组页面已实现；排期等业务按后续任务接入，不导入演示数据。

T14通过 `0002_poll_structure` 新增排期、参与者、时段三表，当前共七张业务表。已有库先备份再显式迁移，原账户、小组和会话保留，见[25号记录](../../Docs/25-排期参与者与时段模型.md)。T15已实现API-04/05草稿创建、整体替换、读取/分页及发布、关闭、取消；UTC时间、权限、冻结与截止细节见[26号记录](../../Docs/26-草稿与排期状态接口.md)，无新迁移或依赖。

T08已将构建后的前端与API接入同一本机服务。平时查看页面只需运行后端，无需同时运行Vite；修改前端后重新构建。

T17新增`0003_votes`迁移和本人答案GET/PUT接口，当前共八张业务表。全量三态答案原子覆盖，服务端取得写锁后检查截止；不接受代填，截止后可回看。升级前备份已有库，迁移后重启；接口、故障回滚与验证见[28号记录](../../Docs/28-本人全量投票接口.md)。填写页面按T18接入。

T19增加`GET /api/v1/polls/{poll_id}/matrix`：组成员可读逐格状态、四类统计及提交进度，同一只读快照、不缓存、未知为null；无新迁移，更新代码后重启服务。契约和验证见[30号记录](../../Docs/30-矩阵与提交进度接口.md)，矩阵页面按T20接入。

T21增加`GET /api/v1/polls/{poll_id}/recommendations`及无数据库/时钟依赖的评分纯函数；每次按当前矩阵快照生成确定性排序和风险解释，不存储分数，无新迁移。接口与验证见[32号记录](../../Docs/32-推荐评分排序与解释.md)。

T24新增`0004_meetings`，当前九张业务表。确认接口在同一事务内重新校验风险、生成会议并更新排期；同候选重试复用原结果，异候选冲突。组成员可按排期读取已有会议核对。已有库先备份再迁移、重启，验证见[35号记录](../../Docs/35-会议确认事务与去重.md)。

T26完成会议详情、小组会议分页和负责人议程/纪要PATCH；纯文本每项最多10000字符，可清空、支持部分更新。无新迁移，重启服务即可加载接口，535项后端回归通过，见[37号记录](../../Docs/37-议程与纪要接口.md)。

## 安装与启动

在PowerShell执行，直接使用虚拟环境里的Python，不需要修改执行策略：

```powershell
cd D:\软件工程\Src\frontend
npm ci
npm run build
cd D:\软件工程\Src\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -m app.db.migrate
.\.venv\Scripts\python.exe -m app
```

已存在本项目的`.venv`时跳过创建步骤；安装过程只作用于该目录。仅运行服务可改装`requirements.txt`，测试使用开发清单。`requirements-dev.in`受运行锁文件约束，避免开发与运行版本不同。

前端构建使用Node 22.20.0，具体依赖见[前端说明](../frontend/README.md)。后端默认绑定`127.0.0.1:8000`，单进程；Ctrl+C停止。访问[正式工程页面](http://127.0.0.1:8000/)或[连接检查](http://127.0.0.1:8000/connection)，另开终端检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

`/api/v1/health`无需登录，数据库可读且结构版本正确时返回`data.status=ok`及本次`request_id`，存储异常时返回503和`STORAGE_UNAVAILABLE`；不返回文件路径或账号信息，不缓存结果。`/livez`仅表示进程存活，数据库暂时不可读时仍可返回ok；两者都不代表完整业务已就绪。

页面深链接可直接打开和刷新。`/assets`提供构建资源；未知API、缺失资源和保留路径保持JSON错误，不回退成HTML。未知页面由Vue显示找不到页面。`/openapi.json`提供本机接口描述；依赖公网CDN的交互文档页未启用。

## 配置

无需创建`.env`也能按默认值启动。要修改时，可参考[.env.example](.env.example)创建未入库的`.env`；不覆盖已有个人配置。系统环境变量优先于`.env`，后者固定从`Src/backend/.env`读取。

| 配置 | 默认值 | 限制 |
| --- | --- | --- |
| MEETFLOW_APP_ENV | local | 只允许local/test |
| MEETFLOW_BIND_HOST | 127.0.0.1 | 首版仅本机，不允许0.0.0.0 |
| MEETFLOW_PORT | 8000 | 1～65535 |
| MEETFLOW_LOG_LEVEL | INFO | DEBUG/INFO/WARNING/ERROR |
| MEETFLOW_DATA_DIR | data | 相对路径始终相对后端目录，避免随终端位置变化 |
| MEETFLOW_FRONTEND_DIR | ../frontend/dist | 前端构建目录，相对路径同样基于后端目录 |

启动先校验配置、数据目录与数据库文件可写性、迁移版本及基础表，再检查前端入口和入口引用的本地构建资源。缺库、错误版本、只读数据库、缺失构建文件都会终止启动。命令行给出简短提示，不输出配置值或堆栈；不会自动迁移、创建表、清库或导入账号。

## 数据库迁移

默认数据库为数据目录下的 `meetflow.sqlite3`。只有显式执行 `python -m app.db.migrate` 才会新建空库或升级版本；重复执行保留现有数据。已有数据升级前先保留备份，不直接修改旧迁移文件。非空无版本库、未知版本库会被拒绝，不将资料文件或其他数据库当作新库覆盖。

`app/db/connection.py`提供已有库连接、结构版本检查及写事务。每个连接启用外键和5秒忙等待；`write_transaction`先取得写锁，再由服务检查时间与状态，异常回滚。启动的写权限探测在事务中写回相同版本值并回滚，不改变已有记录；运行中的健康检查只读，不探测写入。

后续表通过新迁移逐步增加，不自动建表或导入演示账号，不提供破坏性降级命令。完整备份恢复流程在T33验证。

## 账户接口

接口前缀为 `/api/v1`：

| 请求 | 说明 |
| --- | --- |
| POST /auth/register | `{username,email,password}`；201返回本人信息，不自动登录；重复用户名/邮箱409 |
| POST /auth/login | `{username,password}`；200设置HttpOnly会话Cookie；错误凭据统一401 |
| GET /users/me | Cookie有效时返回本人`{id,username,email}`；否则401 |
| POST /auth/logout | 正文`{}`；撤销会话并删除Cookie；已撤销令牌重复退出仍200 |

用户名和邮箱trim后转小写；密码不trim，注册要求8～128字符且非纯空白。密码采用随机盐scrypt哈希；会话为32随机字节令牌，数据库仅保存SHA-256摘要，有效期固定8小时，不续期。成功登录替换当前浏览器会话，其他浏览器会话保留。无需配置签名密钥，没有默认密码或演示账号。

Cookie名为 `meetflow_session`，HttpOnly、SameSite=Strict、Path=/，本机HTTP不设Secure。需要保存Cookie的命令行请求可用PowerShell的WebSession，或其他支持Cookie容器的HTTP客户端；不要把密码和令牌放入URL或提交到仓库。注册登录页面与路由守卫见[21号记录](../../Docs/21-注册登录页面与守卫.md)。

API检查Origin及Sec-Fetch-Site，写请求要求application/json，正文上限256KiB（含流式内容）。本机命令行可省略浏览器来源头；浏览器开发代理须保留Host。数据库忙返回503 DB_BUSY，存储故障返回503 STORAGE_UNAVAILABLE，事务失败不下发成功Cookie。

日志只记录服务端生成的request_id、已验证用户ID、方法、路由模板、状态及耗时，不记录邮箱、正文、查询字符串、Cookie、密码、令牌或异常原文。完整边界与实际结果见[20号记录](../../Docs/20-认证与会话接口记录.md)。

## 目录和验证

```text
app/
  __main__.py       # python -m app，使用经过校验的本机配置
  main.py           # create_app与生命周期
  api/system.py     # /livez与/api/v1/health
  api/auth.py       # 注册、登录、退出与当前用户
  auth/             # 输入模型、密码、会话服务与认证依赖
  web.py            # 前端构建检查、静态资源与SPA回退边界
  common/           # 配置、统一响应、错误与请求上下文
  db/               # 连接、基础表、显式迁移入口和事务
migrations/         # 冻结的Alembic版本文件
tests/              # 独立临时目录、迁移、约束、接口和启动验证
```

在后端目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

测试使用独立临时目录与最小前端文件，不依赖实际dist，也不改开发数据。覆盖配置、迁移、静态托管、健康、认证、小组及来源边界；验证到期、撤销、重启保留、容量并发、写锁和失败回滚。真实浏览器检查见前端`npm run check:auth`、`npm run check:groups`。小组接口与权限规则见[23号记录](../../Docs/23-小组成员与邀请码接口.md)。测试专用路由只在测试内注册，不进入产品应用。

依赖调整时用本项目环境安装`pip-tools==7.6.2`，重新生成两份锁文件，再安装和测试：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --output-file requirements.txt requirements.in
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --output-file requirements-dev.txt requirements-dev.in
```

历史结果见[17号记录](../../Docs/17-后端基础工程记录.md)、[18号记录](../../Docs/18-前端与数据库工程记录.md)，当前同源运行结果见[19号记录](../../Docs/19-本机同源运行与健康检查.md)，表单约定见[16号规范](../../Docs/16-表单与状态展示规范.md)。生命周期和配置分别参考[FastAPI官方说明](https://fastapi.tiangolo.com/advanced/events/)及[Pydantic Settings官方说明](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)。

本轮Python下载连接出现TLS中断，锁文件通过从官方PyPI下载、校验SHA-256的本地wheel缓存生成，保留了原依赖版本；缓存不提交。正常安装仍直接使用上述哈希锁文件，不需要编译命令注释中的本机缓存。
