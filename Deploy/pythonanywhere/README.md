# PythonAnywhere 首次部署

适用：已创建并运行 meetflow-probe，原网站命令指向 ~/meetflow-probe/probe.py，使用 ~/meetflow-probe/venv。安装不购买资源、不读取平台令牌、不上传本机数据库，不包含演示账号或SMTP凭据。

1. 在 Files 页面将 meetflow-pythonanywhere.zip 上传到 /home/mrrrxxxi。
2. 在 Bash 控制台运行：

```bash
unzip -n ~/meetflow-pythonanywhere.zip -d ~
python3.13 ~/meetflow-release/install.py --domain mrrrxxxi.pythonanywhere.com
```

3. 安装显示 MeetFlow prepared 后再运行：

```bash
pa website reload --domain mrrrxxxi.pythonanywhere.com
```

安装使用带哈希锁文件及 no-cache-dir，复用探针虚拟环境。生产库新建于 ~/meetflow-data，和代码分开；若已存在数据库、配置或回滚文件，拒绝重装，按更新流程处理。SMTP默认未配置，找回邮件暂不启用。

平台入口限定 DOMAIN_SOCKET 为 /var/sockets/当前域名/app.sock，且请求实际来自该Unix套接字；只在此条件下解释平台HTTPS头，取X-Forwarded-For末项作为连接IP，拒绝TCP或已被其他代理中间件改写的请求。无转发IP时使用共享未知客户端限流，不接受任意前项伪造IP。本地TCP入口保持原策略。

重载后检查 /api/v1/health、/login、/register、登录及深链接，然后验证重载后新建数据保留。未配置真实邮箱时不要将改密页面可见等同于邮件可用。首次访问为空站，需自行注册实际账号。

若重载后出错，在 Bash 中恢复原探针文件：

```bash
cp ~/meetflow-probe/probe.py.before-meetflow ~/meetflow-probe/probe.py
pa website reload --domain mrrrxxxi.pythonanywhere.com
```

这只回退入口，不删除生产数据。保留错误日志用于排查，不公开令牌、密码或完整Cookie。

参考：[ASGI部署](https://help.pythonanywhere.com/pages/ASGICommandLine/)、[平台客户端IP说明](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses)。
