# MeetFlow 数据库、API 与页面设计

## 1. 数据库设计

字段名称建议使用 `snake_case`，主键建议使用 UUID 或整数；全项目统一即可。所有业务表建议包含 `created_at` 和 `updated_at`。

### 1.1 users 用户表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 用户唯一标识 |
| username | 字符串 | 唯一、非空 |
| email | 字符串 | 唯一、非空 |
| password_hash | 字符串 | 非空，不得保存明文密码 |
| display_name | 字符串 | 显示名称 |
| avatar_url | 字符串 | 可空 |
| is_active | 布尔 | 默认 true |
| is_admin | 布尔 | 默认 false |

### 1.2 groups 小组表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 小组唯一标识 |
| name | 字符串 | 非空 |
| description | 文本 | 可空 |
| owner_id | 外键 | 指向 users |
| invite_code | 字符串 | 唯一、非空 |
| invite_enabled | 布尔 | 默认 true |

### 1.3 group_members 小组成员表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 成员关系标识 |
| group_id | 外键 | 指向 groups |
| user_id | 外键 | 指向 users |
| role | 枚举 | OWNER、MANAGER、MEMBER |
| joined_at | 时间 | 加入时间 |

唯一约束：`(group_id, user_id)`。

### 1.4 scheduling_polls 排期表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 排期唯一标识 |
| group_id | 外键 | 所属小组 |
| creator_id | 外键 | 发起人 |
| title | 字符串 | 非空 |
| description | 文本 | 可空 |
| location | 字符串 | 可空 |
| response_deadline | 时间 | 填写截止时间 |
| status | 枚举 | DRAFT、OPEN、CLOSED、CONFIRMED、CANCELLED |

### 1.5 poll_participants 排期参与者表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 参与关系标识 |
| poll_id | 外键 | 指向 scheduling_polls |
| user_id | 外键 | 指向 users |
| importance | 枚举 | REQUIRED、NORMAL |
| submitted_at | 时间 | 可空，最后完整提交时间 |

唯一约束：`(poll_id, user_id)`。

### 1.6 poll_time_slots 候选时间段表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 时间段标识 |
| poll_id | 外键 | 所属排期 |
| start_at | 时间 | 非空 |
| end_at | 时间 | 非空且晚于 start_at |

唯一约束：`(poll_id, start_at, end_at)`。

### 1.7 availability_votes 空闲状态表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 投票标识 |
| poll_id | 外键 | 冗余但便于查询，可由实现决定是否保留 |
| slot_id | 外键 | 指向 poll_time_slots |
| user_id | 外键 | 指向 users |
| availability | 枚举 | AVAILABLE、MAYBE、UNAVAILABLE |
| note | 字符串 | 可空，简短说明 |

唯一约束：`(slot_id, user_id)`。

### 1.8 meetings 会议表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 会议标识 |
| group_id | 外键 | 所属小组 |
| poll_id | 外键 | 来源排期，可空 |
| selected_slot_id | 外键 | 已确认候选时间，可空 |
| title | 字符串 | 非空 |
| start_at | 时间 | 非空 |
| end_at | 时间 | 非空 |
| location | 字符串 | 可空 |
| agenda | 文本 | 可空 |
| minutes | 文本 | 可空 |
| status | 枚举 | SCHEDULED、IN_PROGRESS、FINISHED、CANCELLED |

### 1.9 tasks 任务表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 任务标识 |
| group_id | 外键 | 所属小组 |
| meeting_id | 外键 | 来源会议，可空 |
| creator_id | 外键 | 创建人 |
| assignee_id | 外键 | 负责人，可空 |
| title | 字符串 | 非空 |
| description | 文本 | 可空 |
| due_at | 时间 | 可空 |
| status | 枚举 | TODO、IN_PROGRESS、DONE、CANCELLED |
| completed_at | 时间 | 完成时填写 |

### 1.10 notifications 站内提醒表（P2）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| id | 主键 | 提醒标识 |
| user_id | 外键 | 接收人 |
| type | 字符串 | 提醒类型 |
| title | 字符串 | 标题 |
| content | 文本 | 内容 |
| related_type | 字符串 | 关联对象类型 |
| related_id | 字符串 | 关联对象ID |
| is_read | 布尔 | 默认 false |

## 2. 关键索引与约束

- 为所有外键建立索引；
- 为 `scheduling_polls(group_id, status)` 建立组合索引；
- 为 `tasks(assignee_id, status, due_at)` 建立组合索引；
- 为 `notifications(user_id, is_read)` 建立组合索引；
- 数据库层和服务层都要验证时间范围；
- 删除小组、排期或用户前必须定义关联数据处理策略；
- 不允许客户端直接提交最终推荐分数，分数只能由后端计算。

## 3. API 设计

统一前缀建议为 `/api/v1`。成功响应返回明确数据模型，错误响应至少包含 `code`、`message` 和可选 `details`。

### 3.1 认证与用户

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | `/auth/register` | 注册 |
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 退出或失效当前会话 |
| GET | `/users/me` | 当前用户信息 |
| PATCH | `/users/me` | 修改个人资料 |

### 3.2 小组

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | `/groups` | 创建小组 |
| GET | `/groups` | 获取我的小组 |
| GET | `/groups/{group_id}` | 获取小组详情 |
| PATCH | `/groups/{group_id}` | 修改小组信息 |
| POST | `/groups/join` | 使用邀请码加入 |
| POST | `/groups/{group_id}/invite-code/reset` | 更新邀请码 |
| GET | `/groups/{group_id}/members` | 获取成员列表 |
| PATCH | `/groups/{group_id}/members/{user_id}` | 修改成员角色 |
| DELETE | `/groups/{group_id}/members/{user_id}` | 移除成员或退出 |

### 3.3 排期、时间段与投票

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | `/groups/{group_id}/polls` | 创建排期 |
| GET | `/groups/{group_id}/polls` | 获取小组排期列表 |
| GET | `/polls/{poll_id}` | 获取排期详情 |
| PATCH | `/polls/{poll_id}` | 修改草稿或允许修改的字段 |
| POST | `/polls/{poll_id}/open` | 开启填写 |
| POST | `/polls/{poll_id}/close` | 提前截止 |
| POST | `/polls/{poll_id}/cancel` | 取消排期 |
| POST | `/polls/{poll_id}/slots` | 添加候选时间段 |
| PATCH | `/polls/{poll_id}/slots/{slot_id}` | 修改候选时间段 |
| DELETE | `/polls/{poll_id}/slots/{slot_id}` | 删除候选时间段 |
| PUT | `/polls/{poll_id}/participants` | 设置参与者和重要程度 |
| PUT | `/polls/{poll_id}/votes/me` | 保存当前用户全部空闲状态 |
| GET | `/polls/{poll_id}/matrix` | 获取时间矩阵 |
| GET | `/polls/{poll_id}/recommendations` | 获取推荐排名与解释 |
| POST | `/polls/{poll_id}/confirm` | 确认候选时间并生成会议 |

### 3.4 会议与任务

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/groups/{group_id}/meetings` | 获取小组会议列表 |
| GET | `/meetings/{meeting_id}` | 获取会议详情 |
| PATCH | `/meetings/{meeting_id}` | 修改议程、地点或纪要 |
| POST | `/meetings/{meeting_id}/finish` | 标记会议结束 |
| POST | `/meetings/{meeting_id}/tasks` | 从会议创建任务 |
| GET | `/groups/{group_id}/tasks` | 获取小组任务 |
| GET | `/tasks/mine` | 获取个人待办 |
| GET | `/tasks/{task_id}` | 获取任务详情 |
| PATCH | `/tasks/{task_id}` | 修改任务内容或状态 |
| DELETE | `/tasks/{task_id}` | 取消或删除任务，策略由实现统一 |

### 3.5 工作台

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/dashboard` | 我的待填写排期、近期会议和临近任务 |
| GET | `/groups/{group_id}/statistics` | 小组任务和会议统计 |

## 4. 页面设计

| 页面 | 核心内容 | 主要操作 |
| --- | --- | --- |
| 产品介绍页 | 产品价值、核心流程、入口 | 注册、登录 |
| 登录/注册页 | 表单和校验信息 | 注册、登录 |
| 个人工作台 | 待填写排期、近期会议、临近任务 | 快速进入对应事项 |
| 小组列表页 | 我创建和加入的小组 | 创建、加入、进入小组 |
| 小组详情页 | 成员、排期、会议、任务摘要 | 管理成员、发起排期 |
| 排期编辑页 | 基本信息、候选时间、参与者 | 保存草稿、开启填写 |
| 空闲状态填写页 | 候选时间网格 | 批量选择、保存、提交 |
| 排期结果页 | 热力图、矩阵、排名、冲突和解释 | 刷新、确认会议 |
| 会议详情页 | 时间、地点、议程、纪要 | 编辑纪要、结束会议 |
| 任务看板 | 按状态分列的任务 | 创建、指派、更新状态 |
| 个人待办页 | 我的全部任务 | 筛选、更新状态 |
| 管理页（P2） | 用户和异常数据 | 禁用或恢复账号 |

## 5. 权限矩阵

| 操作 | 普通成员 | 小组管理员 | 小组负责人 | 系统管理员 |
| --- | :---: | :---: | :---: | :---: |
| 查看所在小组 | 是 | 是 | 是 | 按维护需要 |
| 填写本人空闲状态 | 是 | 是 | 是 | 否 |
| 创建排期 | 否 | 是 | 是 | 否 |
| 设置必到成员 | 否 | 是 | 是 | 否 |
| 确认会议 | 否 | 是 | 是 | 否 |
| 管理成员 | 否 | 有限 | 是 | 否 |
| 转让负责人 | 否 | 否 | 是 | 否 |
| 更新本人任务状态 | 是 | 是 | 是 | 否 |
| 编辑会议纪要 | 经授权 | 是 | 是 | 否 |
| 维护系统账号 | 否 | 否 | 否 | 是 |

## 6. 推荐结果示例

```json
{
  "slot_id": "slot-01",
  "required_unavailable_count": 0,
  "available_count": 5,
  "maybe_count": 1,
  "unavailable_count": 0,
  "unsubmitted_count": 1,
  "score": 27,
  "rank": 1,
  "reason": "全部必到成员均可参加，5人有空、1人勉强参加，关键成员冲突最少。"
}
```

推荐接口不得只返回总分，必须返回构成总分所需的统计项，方便前端解释与测试。
