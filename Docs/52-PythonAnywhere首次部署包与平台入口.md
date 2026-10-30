# PythonAnywhere 首次部署包与平台入口

日期：2026-10-30。账号mrrrxxxi。公网最小探针已由用户创建；本轮实测HTTPS返回200及`{"status":"ok","project":"MeetFlow deployment probe"}`。这证明探针可达，不等于完整项目或持久数据验证完成。

## 已准备的完整包

构建脚本：[build_release.py](../Src/scripts/build_release.py)。只打包后端app/migrations的Python源码、哈希锁文件、前端构建index/assets和安装说明。排除私密.env、数据库、测试数据、依赖目录、缓存和源码映射；拒绝目录外文件及符号链接。已有同名ZIP不覆盖。

本机包位置：`Src/backend/data/releases/meetflow-pythonanywhere.zip`，180646字节。SHA-256为`888a03580ffac3da9d3f414d2705f94580d685ebc9a6263099e1364798735a34`。包在忽略目录，不将构建ZIP和依赖轮子加入源码仓库。复现构建前先运行前端npm run build，再给构建脚本指定一个新的输出文件。

安装脚本和操作：[部署说明](../Deploy/pythonanywhere/README.md)。在Files中上传到账号主目录，Bash执行unzip及install.py；显示准备完成后重载。保留现有探针命令，安装脚本备份原probe.py后将其改为完整应用入口，因此无需删除网站或改变平台API令牌。生产数据新建于~/meetflow-data，SMTP默认未启用。安装依赖前先检查状态；已有数据、配置或回滚文件时拒绝首次安装，避免重复覆盖。

## 平台入口边界

PythonAnywhere把HTTP请求通过DOMAIN_SOCKET交给Uvicorn。通用TCP可信代理IP配置不能直接代表Unix套接字，因此增加专用[hosting.py](../Src/backend/app/hosting.py)入口。

- 仅允许生产环境，DOMAIN_SOCKET必须精确等于`/var/sockets/配置域名/app.sock`。
- 仅在实际ASGI server为该套接字、原client为None时解释转发头；TCP或已被其他中间件改写的地址被拒绝。
- HTTPS转发头必须唯一且为https；使用X-Forwarded-For末项的合法IP，忽略可伪造的前项。重复或非法IP保持未知客户端共享限流，不以任意文本作为新身份。
- 内层继续执行已有Host、来源、Cookie、CSP及账户限流。未放宽默认本机绑定和通用可信代理规则。

依据：[ASGI命令与DOMAIN_SOCKET](https://help.pythonanywhere.com/pages/ASGICommandLine/)、[平台仅保证转发IP末项](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses)。真实平台请求头及完整入口仍需上传后验收，不能将本地构造的套接字测试记为平台已通过。

## 本轮验证

37项后端专项通过，覆盖专用套接字边界、伪造IP不绕过限流、生产Cookie及既有公网配置。40项仓库检查通过，新增打包排除敏感文件和安装状态保护。正式前端构建通过；没有改动界面或默认后端业务逻辑。

实际ZIP解压到临时目录后，生成独立生产配置、新库迁移及validate_runtime均通过，原探针文件不变。Linux x86_64/Python3.13的22个锁定依赖轮子已下载并按锁定哈希验证；平台pip安装结果仍待实际执行。[原始结果](evidence/pythonanywhere-release.json)。

本轮未替换公网网站，当前仍为最小探针。下一步：用户上传ZIP并执行安装/重载 → 验证HTTPS、静态资源、注册登录、深链接及Host/来源边界 → 在两次平台重载前后核对测试数据 → 再接入真实邮件及人工试用。若失败，恢复原probe.py备份并重载，保留生产库排查。

## 首次上传后的HTTPS阻断排查

用户上传完整包并重载后，HTTPS页面返回HTTPS_REQUIRED，说明请求已进入专用入口，但不满足唯一X-Forwarded-Proto=https的假设。平台真实协议头尚未采集，不能宣称部署完成。[官方论坛同类ASGI问题](https://www.pythonanywhere.com/forums/topic/36596/)也说明TLS终止后应用识别协议可能受平台转发限制。

入口增加失败诊断：仅返回ASGI协议和七种常见协议头的固定枚举分类；未知值统一other，不回传Cookie、Authorization、IP或任意原始头值。仍拒绝非HTTPS或模糊协议，未增加可信头和放宽传输边界。38项后端专项通过，包括敏感字段不泄露及错误响应禁止缓存。

下一步只更新远端backend/app/hosting.py并重载，采集错误details中的协议分类。首次安装脚本不能重复执行，不覆盖.env、生产数据库和probe.py备份。确认平台信号之后，再决定兼容适配或部署路径调整；旧ZIP仍为原始首次发布包，未悄悄替换其中内容。
