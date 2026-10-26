# MeetFlow 源代码目录

本目录存放原型、正式前后端与验证工具：

```text
Src/
├── prototype/ # T02静态交互原型与原型规则/浏览器验证
├── backend/   # FastAPI 后端、数据库迁移与 Pytest 测试
├── frontend/  # Vue 3 前端与 Vitest 测试
└── scripts/   # 演示数据、启动和检查脚本
```

编码前请先阅读：

- `../Docs/03-需求边界与MVP.md`；
- `../Docs/05-本地Agent技术实施文档.md`；
- `../Docs/06-数据库API与页面设计.md`；
- `../Docs/07-验收标准与测试计划.md`；
- `../Docs/08-分阶段开发与Agent提示词.md`。

当前已形成需求V1.2、设计V1.0、文档基线B1、T02原型P0.3及正式工程，T09认证接口已实现，完整业务继续推进。完整需求和设计分别见[09](../Docs/09-需求分析文档.md)、[12](../Docs/12-系统设计文档.md)，版本关系见[13](../Docs/13-版本与变更记录.md)。

T05～T08工程基础已实现：按[frontend/README](frontend/README.md)构建前端，再按[backend/README](backend/README.md)显式迁移并启动后端，即可从8000端口访问页面和API。`/api/v1/health`检查数据库可读性与结构版本，`/livez`只表示进程存活；开发仍可用Vite代理。规范见[16](../Docs/16-表单与状态展示规范.md)，历史结果见[17](../Docs/17-后端基础工程记录.md)、[18](../Docs/18-前端与数据库工程记录.md)，当前运行验证见[19](../Docs/19-本机同源运行与健康检查.md)。

T09认证接口见[20号记录](../Docs/20-认证与会话接口记录.md)，T10登录表单和路由守卫见[21号记录](../Docs/21-注册登录页面与守卫.md)。正式工程需要自行注册账号，无自动登录演示账号。

T12接口见[23号记录](../Docs/23-小组成员与邀请码接口.md)，T13小组列表、创建/加入、成员和邀请码管理已接入页面，见[24号记录](../Docs/24-小组页面与交互验证.md)。下一项T14实现排期相关模型。

预览原型：在仓库根目录执行 `python Src/scripts/preview_prototype.py`。原型说明见[这里](prototype/README.md)，截图与本轮结果见[14](../Docs/14-交互原型与验证记录.md)。原型规则测试：`node --test Src/prototype/model.test.mjs`。


## 仓库检查与双平台同步

T03设计图导出工具独立位于[scripts/diagrams](scripts/diagrams/README.md)，只用于报告素材；它与产品前后端依赖分开。图源、图片及原型差异交接见[15号记录](../Docs/15-设计图与需求原型核对.md)。

在仓库根目录运行（仅依赖 Python 标准库与 Git）：

```powershell
python -m unittest discover -s Src/scripts -p "test_*.py" -v
python Src/scripts/sync_remotes.py
```

先检查并提交本地修改，再运行同步脚本。脚本将当前分支推送至 `gitee` 和 `github`，携带可达的附注标签，并验证两个远程分支均与本地提交一致。任一平台失败都会返回失败状态；修复后重新运行即可。工作区中尚未提交的修改不会上传。

这些测试验证仓库结构、文档链接、需求与验收追踪、任务依赖、图文来源、忽略规则及双平台同步的失败处理；它们不代表业务功能已实现或通过测试。

当前仓库在 Windows 上使用系统证书库（`http.sslBackend=schannel`）校验 HTTPS。首次推送若需要登录，请通过 Git 凭据管理器完成认证。
