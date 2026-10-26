# MeetFlow 源代码目录

本目录用于存放项目源代码。开始编码后建议结构如下：

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

当前已形成需求V1.2、设计V1.0、文档整理基线B1和T02交互原型P0.3，暂未生成正式业务代码。完整需求和设计分别见[09](../Docs/09-需求分析文档.md)、[12](../Docs/12-系统设计文档.md)，版本关系见[13](../Docs/13-版本与变更记录.md)。

预览原型：在仓库根目录执行 `python Src/scripts/preview_prototype.py`。原型说明见[这里](prototype/README.md)，截图与本轮结果见[14](../Docs/14-交互原型与验证记录.md)。原型规则测试：`node --test Src/prototype/model.test.mjs`。


## 仓库检查与双平台同步

在仓库根目录运行（仅依赖 Python 标准库与 Git）：

```powershell
python -m unittest discover -s Src/scripts -p "test_*.py" -v
python Src/scripts/sync_remotes.py
```

先检查并提交本地修改，再运行同步脚本。脚本将当前分支推送至 `gitee` 和 `github`，携带可达的附注标签，并验证两个远程分支均与本地提交一致。任一平台失败都会返回失败状态；修复后重新运行即可。工作区中尚未提交的修改不会上传。

这些测试验证仓库结构、文档链接、需求与验收追踪、任务依赖、图文来源、忽略规则及双平台同步的失败处理；它们不代表业务功能已实现或通过测试。

当前仓库在 Windows 上使用系统证书库（`http.sslBackend=schannel`）校验 HTTPS。首次推送若需要登录，请通过 Git 凭据管理器完成认证。
