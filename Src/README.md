# MeetFlow 源代码目录

本目录用于存放项目源代码。开始编码后建议结构如下：

```text
Src/
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

当前仓库处于立项与需求准备阶段，暂未生成业务代码。


## 仓库检查与双平台同步

在仓库根目录运行（仅依赖 Python 标准库与 Git）：

```powershell
python -m unittest discover -s Src/scripts -p "test_*.py" -v
python Src/scripts/sync_remotes.py
```

先检查并提交本地修改，再运行同步脚本。脚本将当前分支推送至 `gitee` 和 `github`，携带可达的附注标签，并验证两个远程分支均与本地提交一致。任一平台失败都会返回失败状态；修复后重新运行即可。工作区中尚未提交的修改不会上传。

这组测试验证仓库结构、README 链接、忽略规则，以及双平台同步的部分失败和远程版本不一致处理；它们不代表业务功能已实现或通过测试。

当前仓库在 Windows 上使用系统证书库（`http.sslBackend=schannel`）校验 HTTPS。首次推送若需要登录，请通过 Git 凭据管理器完成认证。
