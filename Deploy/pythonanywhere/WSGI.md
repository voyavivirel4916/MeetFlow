# 常规 Web/WSGI 备用部署入口

**2026-10-31结论：不再推荐在PythonAnywhere常规Web服务上使用此方案。用户实际收到504-backend；官方说明常规Web不支持线程，而a2wsgi依赖后台线程。本地适配测试不能覆盖这一平台限制。尚无服务器日志，不能把线程限制记为本次504的已证实唯一原因。公网尝试停止，以下为历史步骤，不应继续照做。**

依据：[官方线程限制](https://help.pythonanywhere.com/pages/AsyncInWebApps/)。不删除现有平台文件或备份，不追加付费资源，不改变本机运行入口。

状态：2026-10-30仅本地验证，尚未切换公网。现有ASGI网站在HTTP和HTTPS访问下均传入scheme=http、X-Forwarded-Proto=http，因此无法从这些信息可靠判断外部TLS；不要关闭生产HTTPS校验或把所有套接字请求标成HTTPS。

备用方案使用PythonAnywhere常规Web服务和a2wsgi转换器。前后端和现有生产库不变。该方案依赖账号可创建常规Web应用，须先查看Web页面；如没有该选项或提示需要付费，应先停下，不能直接删除现有ASGI站点。

## 准备和切换顺序

1. 确认账号Web页面可使用Manual configuration及Python 3.13；若可选版本不同，必须重建匹配版本的虚拟环境并验证依赖。
2. 更新backend/app/hosting_wsgi.py，上传本目录requirements-wsgi.txt，在既有虚拟环境中用`pip install --require-hashes --only-binary=:all: -r requirements-wsgi.txt`安装锁定适配库。仅增加依赖，不重复执行首次安装脚本。
3. 复用backend/.env及~/meetflow-data。先备份生产库、记录现有`pa website get --domain mrrrxxxi.pythonanywhere.com`命令和回退配置。不得上传本机库、演示账号或覆盖.env。
4. 仅在常规Web可创建、配置文件已准备且回退路径明确后切换同域名；若平台要求先移除ASGI站点，届时单独处理。当前文档不要求用户立即删除网站。
5. 常规Web虚拟环境指向`/home/mrrrxxxi/meetflow-probe/venv`，WSGI配置文件内容如下。不要继续使用app.hosting的ASGI套接字入口。

```python
import sys
sys.path.insert(0, '/home/mrrrxxxi/meetflow-release/backend')
from app.hosting_wsgi import create_wsgi_app
application = create_wsgi_app()
```

6. 如Web页面提供Force HTTPS则启用并重载；保留应用的HTTPS拒绝检查作为后备。必须实测HTTPS首页、静态资源、深链接、注册登录、安全Cookie，以及HTTP不可访问业务；再验证两次平台重载后的记录保留。转换器不代表平台协议环境已经验证。

## 边界与限制

- 只在显式WSGI工厂中加载a2wsgi，普通ASGI/本地入口不增加运行依赖。开发依赖包含适配库用于回归。
- 仅使用服务器生成的`wsgi.url_scheme`，不以HTTP_X_FORWARDED_PROTO等用户可传递的头改写协议。若服务器仍将HTTPS标为http，继续拒绝访问，需处理平台配置。
- 只有专用平台WSGI入口解析X-Forwarded-For末项合法IP；未知地址共享限流，不采信可伪造前项。
- 转换器不运行ASGI lifespan。当前lifespan仅做运行目录、数据库版本和前端文件验证，因此工厂在接请求前显式执行同一验证；未来添加启动资源时必须重新评估。
- 此适配仅用于普通HTTP功能，不支持WebSocket；现有项目不使用WebSocket。平台重载、真实邮件及人工试用仍需单独验收。

参考：[平台常规Web配置](https://help.pythonanywhere.com/pages/Flask/)、[Force HTTPS](https://help.pythonanywhere.com/pages/ForcingHTTPS/)、[官方客户端IP说明](https://help.pythonanywhere.com/pages/WebAppClientIPAddresses/)、[a2wsgi维护者文档](https://github.com/abersheeran/a2wsgi)。
