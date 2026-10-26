# MeetFlow 后端工程

T05已建立应用工厂、配置、启动检查、统一响应/错误和请求日志。运行基准为Windows、Python 3.11.9，依赖版本与哈希锁定在`requirements.txt`及`requirements-dev.txt`。

T07已加入SQLite连接、显式Alembic迁移和独立测试库；当前迁移建立账户、会话、小组和成员四张基础表。认证、小组、排期等业务按T09之后的任务逐步接入，不导入演示数据，也不宣称业务已经就绪。

## 安装与启动

在PowerShell执行，直接使用虚拟环境里的Python，不需要修改执行策略：

```powershell
cd D:\软件工程\Src\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -m app.db.migrate
.\.venv\Scripts\python.exe -m app
```

已存在本项目的`.venv`时跳过创建步骤；安装过程只作用于该目录。仅运行服务可改装`requirements.txt`，测试使用开发清单。`requirements-dev.in`受运行锁文件约束，避免开发与运行版本不同。

服务默认绑定`127.0.0.1:8000`，单进程；Ctrl+C停止。另开终端检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/livez
```

`/livez`返回`data.status=ok`及本次`request_id`，说明应用进程已启动。它不检查数据库和业务能力。正式`/api/v1/health`与数据库版本启动检查在T08接入；当前访问health为404。`/openapi.json`提供本机接口描述；框架依赖公网CDN的交互文档页未启用。

## 配置

无需创建`.env`也能按默认值启动。要修改时，可参考[.env.example](.env.example)创建未入库的`.env`；不覆盖已有个人配置。系统环境变量优先于`.env`，后者固定从`Src/backend/.env`读取。

| 配置 | 默认值 | 限制 |
| --- | --- | --- |
| MEETFLOW_APP_ENV | local | 只允许local/test |
| MEETFLOW_BIND_HOST | 127.0.0.1 | 首版仅本机，不允许0.0.0.0 |
| MEETFLOW_PORT | 8000 | 1～65535 |
| MEETFLOW_LOG_LEVEL | INFO | DEBUG/INFO/WARNING/ERROR |
| MEETFLOW_DATA_DIR | data | 相对路径始终相对后端目录，避免随终端位置变化 |

启动先校验配置，并用自动清理的临时文件检查数据目录可写。错误配置或不可写目录使启动失败，提示不输出配置值。启动不会自动创建表、清库或覆盖已有文件。

## 数据库迁移

默认数据库为数据目录下的 `meetflow.sqlite3`。只有显式执行 `python -m app.db.migrate` 才会新建空库或升级版本；重复执行保留现有数据。已有数据升级前先保留备份，不直接修改旧迁移文件。非空无版本库、未知版本库会被拒绝，不将资料文件或其他数据库当作新库覆盖。

`app/db/connection.py`提供已有库连接、结构版本检查及写事务。每个连接启用外键和5秒忙等待；`write_transaction`先取得写锁，再由服务检查时间与状态，异常回滚。结构版本检查函数已具备，但尚未接入启动流程，所以此阶段即使未迁移也能启动存活探针。T08将补上启动与健康检查。

后续表通过新迁移逐步增加，不自动建表或导入演示账号，不提供破坏性降级命令。完整备份恢复流程在T33验证。

会话与凭据配置随T09加入，不放置可复用的默认密钥。当前请求日志只记录服务端生成的request_id、方法、匹配路由模板、状态及耗时，不记录正文、查询字符串、Cookie、令牌或异常原文；后续认证完成再加入经验证的用户ID。

## 目录和验证

```text
app/
  __main__.py       # python -m app，使用经过校验的本机配置
  main.py           # create_app与生命周期
  api/system.py     # /livez
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

测试使用独立临时目录，不改开发数据。除配置、启动和接口基础检查外，覆盖空库迁移、重复升级保留数据、模型一致性、缺库不创建、错误版本拒绝、外键与唯一约束、写锁、回滚及中文特殊字符路径。测试专用路由只在测试内注册，不进入产品应用。

依赖调整时用本项目环境安装`pip-tools==7.6.2`，重新生成两份锁文件，再安装和测试：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --output-file requirements.txt requirements.in
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --output-file requirements-dev.txt requirements-dev.in
```

T05历史范围见[17号记录](../../Docs/17-后端基础工程记录.md)，当前T06/T07交付见[18号记录](../../Docs/18-前端与数据库工程记录.md)，表单反馈约定见[16号规范](../../Docs/16-表单与状态展示规范.md)。生命周期和配置实现分别参考[FastAPI官方说明](https://fastapi.tiangolo.com/advanced/events/)及[Pydantic Settings官方说明](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)。
