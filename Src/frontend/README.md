# MeetFlow 正式前端

T06建立 Vue 3、TypeScript、Vite、Vue Router 和 API 客户端，沿用暖白、靛蓝、珊瑚橙风格。T10登录、T13小组、T16排期编辑/发布、T18三态填写、T20矩阵、T23推荐、T25会议确认、T27会议详情及T29任务与待办已接入真实接口。[T02原型](../prototype/README.md)单独保留。

T25在结果页提供负责人结束收集、选择候选和风险确认弹窗；有风险或非首位须勾选并写理由。响应丢失时只读核对，不自动重复确认。运行`npm run check:confirmation-ui`验证；交互、截图和复现见[36号记录](../../Docs/36-会议确认交互与验证.md)。

T27在已确认结果提供“查看会议”，进入详情后组员只读，负责人可编辑议程与纪要；保存不确定时保留输入、先核对。运行`npm run check:meeting-ui`验证，见[38号记录](../../Docs/38-会议详情与纪要页面.md)。

T29在会议内创建任务，小组查看全部任务，个人待办默认未完成；负责人或执行人切换三态。状态更新失败先核对，创建响应丢失后可明确重试原标识去重。运行`npm run check:tasks-ui`验证，见[40号记录](../../Docs/40-任务列表与个人待办页面.md)。

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
npm run check:groups
npm run check:groups-ui
npm run check:polls
npm run check:poll-editor
npm run check:votes-ui
npm run check:matrix-ui
npm run check:recommendations-ui
$env:PROTOTYPE_BROWSER='msedge'
npm run check:auth
```

先运行 `npm run build`。检查脚本显式迁移独立临时数据库；`check:browser`验证Vite开发代理，`check:delivery`只启动后端并验证正式构建的同源页面。使用空闲端口，结束后清理，不使用开发数据库或占用8000/5173。加 `-- --screenshots` 更新对应截图。本轮结果与截图见[19号记录](../../Docs/19-本机同源运行与健康检查.md)，T06/T07历史结果见[18号记录](../../Docs/18-前端与数据库工程记录.md)。

`check:auth`验证真实Cookie、跨来源表单和多会话隔离；`check:auth-ui`验证登录页；`check:groups`验证小组接口；`check:groups-ui`验证小组页面；`check:polls`验证排期接口；`check:poll-editor`验证编辑、发布和异常核对。开发代理可用 `node browser.check.mjs --poll-editor --groups-ui --auth-ui`。结果见[20号](../../Docs/20-认证与会话接口记录.md)、[21号](../../Docs/21-注册登录页面与守卫.md)、[23号](../../Docs/23-小组成员与邀请码接口.md)、[24号](../../Docs/24-小组页面与交互验证.md)、[26号](../../Docs/26-草稿与排期状态接口.md)和[27号记录](../../Docs/27-负责人排期编辑与发布.md)。

`check:votes-ui`验证T18真实三态填写、完整校验、保存回显、断连核对、关闭只读及权限；开发代理用`node browser.check.mjs --votes-ui`。说明与截图见[29号记录](../../Docs/29-空闲状态填写页面.md)。

`check:matrix-ui`验证T20矩阵、进度、读取失败恢复、访问权限和20×15键盘滚动；开发代理用`node browser.check.mjs --matrix-ui`。说明与截图见[31号记录](../../Docs/31-矩阵与提交进度页面.md)。

`check:recommendations-ui`验证T23真实排名、分数组成、必到风险、全时段冲突及失败保留；开发代理用`node browser.check.mjs --recommendations-ui`。说明与截图见[34号记录](../../Docs/34-推荐结果与冲突提示页面.md)。
