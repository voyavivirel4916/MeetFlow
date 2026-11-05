# MeetFlow 项目介绍站点

公开地址：https://voyavivirel4916.github.io/MeetFlow/ 。发布状态以GitHub Actions和该地址实际响应为准，不把开启Pages配置等同于发布成功。

独立的长页介绍站点，使用HTML/CSS/JavaScript；不是PPT转换页。页面有协作便签示意、真实应用截图切换、流程说明、演示包下载和常见问题。图片来自独立演示环境，数据为虚构样例。

## 本地预览

在仓库根目录运行`python -m http.server 8770 --bind 127.0.0.1 --directory Site`，打开 http://localhost:8770/ 。这里的静态服务与8002上的完整应用相互独立。

## GitHub Pages

仓库Settings → Pages → Build and deployment → Source选GitHub Actions。工作流`.github/workflows/pages.yml`仅上传Site目录，不上传真实数据库、环境配置、项目课件或PPT。后续修改Site并推送main会重新发布。

页面为公开的软件介绍与获取入口，完整业务仍在用户本机运行，不能把站点上线写成多人云端应用已经验收。课程要求保留网站至少一个月；请保持仓库与Pages可访问，2026年11月5日上线后至少保留到12月5日。

## 演示包

下载文件：`downloads/MeetFlow-Windows-Demo.zip`。另见[跨电脑说明源文件](../Deploy/portable/另一台电脑演示说明.md)。

打包命令：`Src/backend/.venv/Scripts/python.exe Src/scripts/build_portable_demo.py`。仅包含业务代码、构建后的页面、启动器、预设展示日期及运行依赖轮子，不复制.venv、真实库、会话、.env或原电脑练习进度。离线依赖针对Windows64位Python3.11，Python本体需事先安装。其他电脑未进行实体机验收，本次在本机新解压目录验证安装和启动，不能写成已适配全部系统。

另一台电脑独立运行与局域网共享是两种方案。当前未放开本地模式的监听限制，也未修改防火墙、HTTPS或来源校验。

## 验证

- `Src/scripts/test_project_site.py`：资源链接、真实性说明、打包排除用户数据、部署目录边界和安装失败路径。
- `Src/scripts/check_project_site.cjs`：1440/975/390宽度、截图加载、切换标签与键盘、FAQ、下载及页面异常。
- `checks.json`记录网页检查；[独立包安装启动证据](../Docs/evidence/portable-demo-20261105.json)记录全新目录离线安装、pip check、健康检查、真实登录、工作台、四人矩阵与任务页面验证。这是在本机的新目录测试，不冒充另一台实体机验收。
