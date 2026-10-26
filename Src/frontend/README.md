# MeetFlow 正式前端

T06建立 Vue 3、TypeScript、Vite、Vue Router 和 API 客户端，沿用暖白、靛蓝、珊瑚橙风格。T10已接入真实注册登录表单和路由守卫；其他业务页面继续待接入。[T02原型](../prototype/README.md)单独保留。

## 本机运行与开发

本轮使用 Node 22.20.0、npm 10.9.3。依赖精确版本和完整性保存在 `package.json`、`package-lock.json`；后续安装用 `npm ci`。

```powershell
cd D:\软件工程\Src\frontend
npm ci
npm run build
```

然后按[后端说明](../backend/README.md)安装、显式迁移并启动服务，访问[同源前端](http://127.0.0.1:8000/)及[连接检查](http://127.0.0.1:8000/connection)。构建后只需运行后端，修改前端后重新构建；后端启动会检查构建入口及其引用文件是否齐全。

开发时可另开终端执行 `npm run dev`，访问[开发前端](http://127.0.0.1:5173/)。Vite只绑定127.0.0.1，端口被占用时报错，将 `/api` 和 `/livez` 代理到8000端口；代理显式保留Host，使浏览器Origin与后端来源校验一致，无需开放跨域权限。仍需已启动的后端和一次有效构建。

| 页面 | 路径 |
| --- | --- |
| 小组列表、详情 | `/groups`、`/groups/:groupId` |
| 发起、编辑排期 | `/groups/:groupId/polls/new`、`/polls/:pollId/edit` |
| 填写、结果 | `/polls/:pollId/vote`、`/polls/:pollId/results` |
| 会议、个人待办 | `/meetings/:meetingId`、`/tasks/mine` |
| 登录、注册 | `/login`、`/register` |
| 临时工程检查页 | `/connection` |

ID只接受正整数字面量，无效地址显示找不到页面。业务路径每次进入前核对服务端会话；未登录转登录页，连接失败转 `/session-check`，不展示受保护内容。`safeReturnPath`只允许已知受保护路径，拒绝外部地址、查询参数和片段。连接检查与404可直接访问。

## API与状态约定

`src/api/client.ts`统一调用同源 `/api/v1/`，携带同源Cookie；处理服务端错误、参数详情和请求编号，默认10秒超时并支持调用者取消，不自动重试。请求编号须与响应头一致。泛型只声明业务数据类型，具体DTO仍须由后续业务模块校验。

提交遇到断连、超时、异常响应或5xx时返回 `uncertain=true`，页面应先读取现状核对，不直接宣称未保存或重新发送。401、403、409、422供后续页面分别处理。共享状态组件以文本、状态区域和警告区域呈现反馈；接口消息通过Vue文本插值显示，不作为HTML执行。

不在localStorage、sessionStorage或URL中保存凭据、答案和表单输入。刷新后重取服务端数据；后续表单的失败保留、离开确认等交互按[16号规范](../../Docs/16-表单与状态展示规范.md)实现。

## 检查

```powershell
npm test
npm run build
npm audit
```

构建输出在被Git忽略的 `dist/`。T08已接入后端同源托管；连接检查调用真实 `/api/v1/health`，数据库不可读或版本不符时展示存储错误，恢复后可再次检查。该结果不表示账户与会议业务完成。

浏览器检查额外需要Playwright和本机Chrome/Edge、已安装依赖的后端。默认从Node环境查找Playwright；可把已安装模块的绝对路径设为 `PLAYWRIGHT_MODULE_PATH`。默认使用后端Windows虚拟环境，其他环境通过 `MEETFLOW_TEST_PYTHON` 指定Python可执行文件：

```powershell
npm run check:browser
npm run check:delivery
npm run check:auth
npm run check:auth-ui
$env:PROTOTYPE_BROWSER='msedge'
npm run check:auth
```

先运行 `npm run build`。检查脚本显式迁移独立临时数据库；`check:browser`验证Vite开发代理，`check:delivery`只启动后端并验证正式构建的同源页面。使用空闲端口，结束后清理，不使用开发数据库或占用8000/5173。加 `-- --screenshots` 更新对应截图。本轮结果与截图见[19号记录](../../Docs/19-本机同源运行与健康检查.md)，T06/T07历史结果见[18号记录](../../Docs/18-前端与数据库工程记录.md)。

`check:auth`验证真实Cookie、跨来源表单和多会话隔离；`check:auth-ui`通过页面操作验证注册、登录、守卫、失败保留和不确定结果恢复。开发代理可用 `node browser.check.mjs --auth --auth-ui`。结果见[20号](../../Docs/20-认证与会话接口记录.md)和[21号记录](../../Docs/21-注册登录页面与守卫.md)。
