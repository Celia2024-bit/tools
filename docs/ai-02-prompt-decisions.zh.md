# 四个 Prompt 的每一条决策，以及为什么

> 面向 presentation 的第 2 份文档。逐条拆解四次 Gemini 调用的 prompt：**每条规则在防什么、不写会发生什么、代码侧有没有兜底。**
>
> 最后一列（"代码侧兜底"）是重点：**一条只写在 prompt 里、代码不检查的规则，等于一句请求；一条 prompt 里写了、代码也查的规则，才是一条约束。** 这个区分贯穿全文，也是 presentation 最有价值的角度。

---

## 0. 四次调用的全景

| # | 位置 | 任务 | 输出 | token 上限 | thinking |
|---|---|---|---|---|---|
| 1 | `nl_dev_tool.py: route_intent()` | **分类**：这句话该用哪个工具 | 4 字段 JSON | 200 | MINIMAL |
| 2a | `nl_to_state_machine.py` | **翻译**：一句话 → 状态机规格 | Markdown（3 张表） | 2000 | MINIMAL |
| 2b | `nl_to_aspect_config.py` | **翻译**：一句话 → 注入配置 | `config.json` | 2000 | MINIMAL |
| 2c | `nl_to_new_interface.py` | **改写**：旧头文件 + 一句话 → 新头文件 | 完整 C++ 头文件 | 2000 | MINIMAL |

**一个观察先摆在这里，它是整个设计的灵魂：这四次调用没有一次是"创作"任务，全部是"分类"或"翻译"。**

这解释了后面所有的决策：分类和翻译任务里，**模型的自由度是成本而不是收益**。所以每个 prompt 都在做同一件事 —— 尽可能把开放式生成压缩成"从有限集合里选"或"往固定模板里填"。

（也正因如此，`temperature` 没设是个疏漏 —— 见坑 A5。翻译任务的正确温度是 0。）

---

## 1. 路由 Prompt（`ROUTER_SYSTEM_PROMPT`）

### 完整规则拆解

| # | prompt 里写了什么 | 为什么 | 不写会怎样 | 代码侧兜底 |
|---|---|---|---|---|
| R1 | `"You are an intent router for C++ automation tools"` | 给模型一个**窄角色**。它不是助手，不是程序员，只是一个分类器 | 模型会倾向于"帮你把事做完"——解释代码、给建议、写代码，而不是只输出一个选择 | 无（也不需要） |
| R2 | 列出 5 个选项，每个带一句说明 | 把开放问题变成**闭集选择**（见 §5 详述） | 模型会自己发明工具名：`"cpp_refactor"`、`"add_logging"` | ✅ **有** —— `main()` 的白名单 else 分支 |
| R3 | `performance_monitor` 的说明特别写了 *"This tool generates nothing and changes no code: it is a live dashboard, and the answer is a link"* | 这个工具和其他三个**性质不同**。不写清楚，模型会因为"其他三个都生成文件"的模式而误以为它也要生成什么 | 模型可能拒绝选它（觉得"这不是代码生成任务"），或选了之后期待有产物 | ✅ 有 —— `handle_performance_monitor()` 根本不碰文件，只打一行 dashboard 链接 |
| R4 | `unsupported` 的说明列举了具体例子：*"general questions (weather, news, math), chit-chat, requests about other languages"* | 抽象的"其他情况"模型判断不了边界。**给反例比给定义有效** | 模型会把"帮我写个 Python 装饰器"硬塞给 aspect_injector（都是"加日志"嘛） | ✅ 有 —— else 分支 + `EXIT_UNSUPPORTED` |
| R5 | **`"Never force an unrelated request onto one of the tools."`** | 这是整个 prompt 里**最重要的一句**。模型的默认行为是"有用"，而"有用"在分类任务里表现为**硬凑一个最接近的答案** | 问"今天天气怎样"→ 模型可能选 `performance_monitor`（都是"看状态"嘛）→ 然后真的去跑了一个工具 | ✅ 有 —— 白名单 + `handle_unsupported()` |
| R6 | `"Output JSON ONLY in this format: {...}"` + 给出确切的字段骨架 | 下游是 `json.loads`，不是人 | 模型输出 `"我觉得应该用 aspect_injector，因为..."` → 解析失败 | ⚠️ 部分 —— `json.loads` 会炸，但没被捕获（坑 A1） |
| R7 | `"Do not wrap in markdown code fences."` | 模型被训练成"输出代码要加围栏" —— 这是它极强的习惯，必须明确禁止 | 输出 ` ```json\n{...}\n``` ` → `json.loads` 失败 | ✅ 有 —— 代码里还是剥了一次 fence（**双保险**，见 §6） |
| R8 | `old_header` / `src_dir` 两个抽取字段，`"if mentioned in description, else null"` | **省一次交互**。用户说了路径就直接用，不用再问一遍。这是 UX 决策 | 用户每次都得额外填两个表单字段，"一句话完成"的体验就没了 | ❌ **没有** —— 这是坑 B1 的来源。抽取错了会静默回退默认目录 |
| R9 | `reason` 字段，`"required when tool is unsupported, else null"` | 拒绝必须**可解释**。前端要把它显示在摘要条上，用户才知道为什么被拒 | 拒绝变成一句冷冰冰的"不支持"，用户不知道该怎么改写请求 | ✅ 有 —— `handle_unsupported()` 里有 fallback 文案：`reason or 'the request does not match any of the tools'` |

### 路由调用的三个参数决策

| 参数 | 值 | 为什么 |
|---|---|---|
| `max_output_tokens` | **200** | 输出只有 4 个短字段，200 绰绰有余。给小一点是为了**省钱省延迟**（路由是每次运行都要跑的那一步）。代价：如果模型话多，会撞上 MAX_TOKENS → `text` 可能为 None（坑 A2/A4） |
| `thinking_level` | **MINIMAL** | 分类任务不需要长推理链。给它思考预算只会增加延迟和 token 消耗，而准确率提升有限 |
| `automatic_function_calling` | **disable** | 我们没有给模型任何可调用的工具。禁掉可以避免 SDK 自动进入多轮循环，让这次调用**严格是一次请求、一次回答** —— 可预测性优先 |

**还有一个"没做的决策"值得讲：路由器不读任何文件。** 它只看用户那句话。理由有三个：
1. 判断"这是状态机任务还是接口任务"根本不需要文件内容
2. 省 token、省延迟
3. **减少 prompt 注入面** —— 文件内容不进 prompt，文件里的恶意注释就影响不了路由决策（对比：`interface_sync` 的生成器必须读文件，那里就有注入面，见坑 D1）

---

## 2. 注入配置 Prompt（`nl_to_aspect_config.py`）

这个 prompt 是四个里**最像 schema 文档**的一个 —— 因为它的下游 `config.py` 校验最严。

| # | 规则 | 为什么 | 不写会怎样 | 代码侧兜底 |
|---|---|---|---|---|
| A1 | 开头声明 *"this is parsed by existing Python code, so be precise"* | 给模型交代**读者是谁**。这会改变它的输出风格：不加解释、不加注释、不"友好化" | 模型倾向于生成带注释的 JSON（JSON 不支持注释）或加一段说明 | — |
| A2 | `Top-level keys allowed: "inject", "remove", "exclude", "include_dirs"` | 直接镜像 `config.py:22` 的 `TOP_LEVEL_KEYS` | 模型会发明 key：`"targets"`、`"rules"`、`"settings"` | ✅ **有且严格** —— 未知 key 直接 `raise ValueError`（不是忽略！） |
| A3 | **`Exactly one of "inject" or "remove" must be present — never both, never neither.`** | 镜像 `resolve_mode_and_rules()` 里的两条 raise。这是一条**互斥约束**，JSON Schema 都表达不了，只能用自然语言说 | 模型可能同时给 inject 和 remove（看起来更"完整"）→ 下游直接报错 | ✅ 有 —— 两条明确的 `raise ValueError` |
| A4 | 逐字段说明，且标注 `or ""` for all | 告诉模型**"不限制"怎么表达** —— 是空字符串，不是省略、不是 null、不是 `"*"` | 模型用 `"*"` 或 `null` 表示"全部" → 被当成字面值去匹配 → 匹配不到任何函数 → **静默 0 改动** | ❌ 没有 —— 空字符串和 `"*"` 对代码是两个不同的字面值 |
| A5 | `"inject_type": a list of one or more of "trace", "validate", "guard"` + 每个的一句解释 | **枚举约束**（见 §5）。而且解释了每个值干什么，这样"给我加异常保护"能被正确映射到 `guard` | 模型写 `"logging"`、`"tracing"`、`"try_catch"` | ❌ **没有** —— 坑 B2：不认识的值被 `if kind not in wanted: continue` **静默跳过** |
| A6 | `"validate": ... (skipped automatically if the function has no parameters)` | 告诉模型**下游的行为**，这样它不必自己去判断"这个函数有没有参数"（它也判断不了，它没看源码） | 模型可能自作聪明地只对"看起来有参数"的函数加 validate → 但它在瞎猜 | ✅ 有 —— 真的是自动跳过的 |
| A7 | `"inject_type" ... Only meaningful for "inject" entries; omit for "remove" entries.` | remove 是按标记删除的，不需要知道类型 | 模型在 remove 规则里塞 inject_type → 无害但是噪声，且暗示了错误的心智模型 | ⚠️ 被忽略（无害） |
| A8 | **`Never include "base_class" here` (exclude 条目)** | 镜像 `resolve_mode_and_rules()` 里那条专门的 raise —— exclude 只在 目录/文件/函数 层面工作 | 模型会很自然地在 exclude 里写 base_class（因为 inject 里可以写）→ 下游报错 | ✅ **有** —— 明确的 `raise ValueError`，还会把出错的条目打印出来 |
| A9 | `"include_dirs" ... only needed when "base_class" filters are used` | 解释**什么时候才需要它**，避免模型每次都加一个用不上的 key | 每个 config 都多一个 `include_dirs: []` —— 无害但是噪声 | ⚠️ 空列表无害 |
| A10 | **`Do not invent restrictions the user didn't ask for.`** | 模型有"帮你想周全"的倾向 —— 会自己加一条 exclude 把 `main.cpp` 排掉 | 少注入了文件，而且**完全静默**（生成的是一份语法合法的 config） | ❌ **没有代码修法**（坑 B3）→ 只能靠 `summarize_aspect_config()` 打印规则 + diff review |
| A11 | `Default inject_type to ["trace"] if the description doesn't say what to inject.` | 给一个**明确的缺省值**，而不是让模型自己挑一个。而且这个缺省值和代码里的 `DEFAULT_INJECT_TYPES = ["trace"]` 一致 | 用户说"给这些函数加点日志"→ 模型可能选 `["trace","validate","guard"]` 三件套 → 注入量爆炸 | ✅ 有 —— `processor.py` 里 `rule.get("inject_type", ["trace"])` 也是同一个缺省 |
| A12 | `Output ONLY the JSON. No commentary, no code fences, no trailing comments.` | 下游 `json.loads` | 解析失败 | ⚠️ 代码里剥了 fence，但 JSON 解析失败没有优雅处理 |

### 这个 prompt 最值得讲的一点

**它是照着 `config.py` 抄的，而不是反过来。** 文件顶部的注释就写了：

```python
# Mirrors config.py's TOP_LEVEL_KEYS and resolve_mode_and_rules exactly.
# Keep this in sync if config.py's schema ever changes.
```

顺序很重要：**先有经过测试的解析器，再有 prompt。** 不是先让 AI 自由输出、再改工具去迁就它。这样做的收益是 `aspect_injector.py` 一行都不用改就能被 AI 驱动；代价是那两份 schema 会漂移（坑 B4）。

---

## 3. 状态机 Prompt（`nl_to_state_machine.py`）

这个 prompt 用了一个和其他三个都不同的手法：**它把整个输出模板内联在 prompt 里。**

````
# <Title> State Machine Definition

## Config
- **prefix**: <PascalCase prefix ...>

## Context Definition Table
| **context_name** | **field_type** | **field_name** | **description** |
| ----------------- | --------------- | --------------- | ----------------- |
...
````

| # | 规则 | 为什么 | 不写会怎样 | 代码侧兜底 |
|---|---|---|---|---|
| S1 | **内联完整模板**（标题、列名、分隔行、占位符） | 这是 **one-shot 结构示范**。对"必须精确匹配的格式"，给一个样板比用文字描述有效得多 —— 模型很擅长填模板，不擅长听描述 | 用文字说"要有一张状态定义表，包含 id、name、type、description 四列"→ 模型会改列序、改大小写、加列、用 `State ID` 这种更好看的表头 | ✅ 有 —— `table_to_json.py` 用表格首行当 dict key，列名必须是 `STATE_COLUMNS` 那几个 |
| S2 | 标题必须是 `## Context/State Definition Table` 等 | `parse_markdown_tables()` 按 `## ` 切段，`_find_section()` 靠**标题关键字**找表 | 找不到标题 → `raise ValueError("Could not find a table titled with 'State Definition'")` | ✅ 有 —— 明确报错，还告诉你期望的标题 |
| S3 | **`Exactly one state must have type "initial". Terminal states get type "final". All other states get "normal".`** | 一台状态机必须有唯一入口。这同时是**枚举约束**（三个值）和**基数约束**（initial 恰好一个） | 模型可能给两个 initial（"下单"和"重新下单"都像起点），或者一个都不给 | ✅ **有且双重** —— `VALID_TYPES` 白名单 + `validate()` 专门检查 0 个 / 多个 initial，有 error 就 `sys.exit(1)`，JSON 根本不生成 |
| S4 | `State ids are S000, S001, ... in order of first appearance` / `Transition ids are T001, T002, ...` | 下游需要**稳定、可预期的 id**。而且固定的编号规则让两次生成的结果可比对（diff 友好） | 模型用 `ST_1`、`state-001`、`1`，或者干脆跳号 | ✅ 部分 —— `validate()` 查重复 id，但不查命名格式 |
| S5 | **`"guard" is only filled in when the description implies a condition`** | 防"AI 加戏"。模型很想给每个转换配一个守卫条件，因为那看起来更专业 | 每个转换都长出一个 `IsValid` 守卫 → 生成的 C++ 里全是你没要求的空守卫函数 → 你得手动删 | ❌ 没有 —— 语义问题，代码判断不了 |
| S6 | **`"action" is only filled in when the description implies a side effect`** | 同上 | 每个转换都长出一个 action 桩 | ❌ 没有 |
| S7 | `Use PascalCase, e.g. SendPaymentNotification` (action) | **action 会变成 C++ 方法名**。`send payment notification` 或 `send-notification` 生成不了合法标识符 | 生成的 C++ 编译失败（响亮失败，不致命） | ⚠️ 间接 —— `g++` 会报错 |
| S8 | `Infer 2-4 sensible context fields if the domain implies them; otherwise leave the Context table with just the header` | 给一个**数量区间**，并明确"可以为空"。context 是状态机携带的数据，模型要么一个不给，要么给十五个 | 不给 → 生成的状态机没有任何数据；给太多 → 一堆你不需要的字段进了生成的 struct | ❌ 没有（空 context 是合法的） |
| S9 | `Output ONLY the Markdown file content. No commentary, no code fences.` | 下游是解析器 | 前言废话会被当成表格外的内容忽略（这次是宽容的），但 fence 会破坏首个 `## ` 的识别 | ⚠️ 宽容解析，部分情况能自愈 |

### 这条链路上最漂亮的一个设计

状态机是唯一一个**下游会做语义校验**的工具。`table_to_json.py` 的 `validate()` 检查了：

- 空的 name / from_state / event / to_state
- 重复的 state id、重复的 state 名、重复的 transition id
- `type` 不在 `{initial, final, normal, ""}` 里
- **initial 状态不是恰好一个**
- 转换引用了未定义的状态（`from_state` / `to_state` 不在状态表里）
- **死状态**：normal 状态没有出边（警告 —— "如果是终态请标 final"）
- **孤儿状态**：定义了但从未出现在任何转换里（警告）
- **冲突转换**：同一个 `(from_state, event, guard)` 指向两个不同的目标（错误）

有 error 就 `sys.exit(1)`，JSON 不生成，`subprocess.run(check=True)` 抛异常，整条流水线中止。

**这就是"AI 只负责翻译，正确性由工具保证"落到实处的样子。** 模型可以生成一台逻辑上矛盾的状态机 —— 而这台状态机**永远不会变成 C++**。presentation 里这一段可以配一句：

> 我没有让 prompt 去保证状态机的逻辑正确性，因为那种保证是不可验证的。我让一个已经写好的校验器去保证 —— 它对手写的表格和 AI 生成的表格一视同仁。

**顺带一个反差：** 注入器侧的 `inject_type` 也是枚举约束，但**没有**这样的白名单校验（坑 B2）。同一个团队、同一套设计哲学，两个工具给了两个不同的答案 —— 这种"自己代码里的不一致"能被自己讲出来，比什么都有说服力。

---

## 4. 接口头文件 Prompt（`nl_to_new_interface.py`）

这个 prompt 最特殊：**输出不是数据格式，而是代码。** 所以它的约束全部是"风格与边界"，而不是"schema"。

| # | 规则 | 为什么 | 不写会怎样 | 代码侧兜底 |
|---|---|---|---|---|
| I1 | **`Preserve the file's existing style exactly: include guards/pragma, brace style, indentation, the virtual destructor, and any methods NOT mentioned`** | **这是整个 prompt 的核心，理由见下面一整节** | 生成一份"更漂亮"的头文件 → diff 里全是噪声 | ❌ 没有 —— 只能靠 diff review |
| I2 | `Every interface method stays a pure virtual method (trailing "= 0;")` | 这是接口（抽象基类）。模型可能"顺手"给个默认实现 | 纯虚变成有实现 → 派生类不再被强制 override → **整个 interface_sync 的前提没了** | ❌ 没有 |
| I3 | **`Never add "override" here — this is the base interface, not a derived class.`** | 模型见过大量派生类代码，`override` 是它的肌肉记忆 | 基类方法带 `override` → 编译错（响亮，还好） | ⚠️ `g++` 会报错 |
| I4 | `Apply only the changes described ... Do not invent unrelated changes.` | 和 A10 / S5 / S6 同一类：**禁止发挥** | 模型顺手把 `int` 改成 `int32_t`、加个 `[[nodiscard]]`、补个注释 → 这些改动会被 `interface_sync.py` 当成真实的接口变更**传播到所有派生类** | ❌ 没有 |
| I5 | **`Keep the class name identical to the input.`** | `interface_sync.py` 靠**类名**去找派生类。类名一变，它一个派生类都找不到 → **静默 0 改动** | 模型把 `IObserver` 改成 `IDataObserver`（"更准确"）→ 同步静默失败 | ❌ 没有（很容易加：断言新旧类名一致） |
| I6 | `Output ONLY the complete C++ header file content. No commentary, no markdown code fences, no explanation.` | 这份输出会**直接被写成 `.h` 文件** | 一句 "Here's the updated header:" 就出现在头文件第一行 → 编译错 | ⚠️ 剥了 fence，但语言标签只认小写（坑 A6） |
| I7 | 输入结构：`"Existing header:\n\n{old}\n\nRequested change:\n\n{description}"` | 把"原文"和"要求"分开 | 拼在一起模型分不清哪部分是要改的对象、哪部分是指令 | ⚠️ 这里也是坑 D1 的来源 —— 文件内容进了 prompt |

### 为什么"保留风格"这条规则值得单独讲十句

这是**整份文档里我最想让你在 presentation 上讲透的一条**，因为它看起来像代码审美偏好，实际上是**架构必需**。

链路是这样的：

```
AI 生成新头文件  →  interface_sync.py 对比 旧头文件 vs 新头文件  →  差异传播到每个派生类
```

关键在于中间那个 **diff**。`interface_sync.py` 的整个工作前提是："新旧两份头文件之间的差异，就是用户想要的接口变更。"

如果模型重新排版了整个文件：

- 缩进从 4 空格变成 2 空格 → **每一行都是差异**
- 大括号从下一行挪到行尾 → **每个方法都是差异**
- `#ifndef` 换成 `#pragma once` → 文件头是差异
- 方法顺序按字母排了序 → 顺序全变

这时候 diff 里有 200 行变化，其中只有 2 行是你真正要的。后果有三层，一层比一层严重：

1. **你没法 review** —— 真实改动淹没在噪声里。而 review 是坑 B3/I4 的**唯一防线**，防线失效。
2. **`interface_sync.py` 可能误判** —— 它要从 diff 里识别"哪些方法被删了、哪些被加了、哪些签名变了"。当格式全变的时候，它可能把"同一个方法换了个缩进"看成"删了一个旧方法 + 加了一个新方法"→ 于是在每个派生类里**删掉一个 override、加一个新桩**。
3. **噪声会被传播** —— 派生类被改的不只是你要的那一处。

所以这条 prompt 规则真正的含义是：

> **让 diff 只包含语义变更，不包含格式变更。**

这句话每个做过 code review 的人都懂 —— "不要把重构和格式化混在一个 commit 里"。这里只是把同一条工程纪律**写进了 prompt**，因为下游消费 diff 的是一个程序，而程序比人更不能容忍噪声。

**presentation 可以这样收尾：** AI 生成代码最常见的问题不是写错，是**风格漂移**。而当你的下游是一个 diff 工具时，风格漂移就从"不好看"升级成"不可用"。

---

## 5. 为什么枚举（闭集）约束这么好用

你问的"为什么用 enum 约束舒服" —— 这值得单独一节，因为它是四个 prompt 共享的核心手法。

### 出现在了哪些地方

| 位置 | 闭集 | 大小 |
|---|---|---|
| 路由 `tool` | `state_machine` / `interface_sync` / `aspect_injector` / `performance_monitor` / `unsupported` | 5 |
| `inject_type` | `trace` / `validate` / `guard` | 3 |
| 状态 `type` | `initial` / `final` / `normal` | 3 |
| config 顶层 key | `inject` / `remove` / `exclude` / `include_dirs` | 4 |

### 好用的五个理由

**① 错误变得"可检测"。** 这是最根本的一条。

- 开放输出：模型回答 `"用重构工具处理一下继承体系"` —— 代码**无法判断这是对还是错**，只能当字符串往下传。
- 闭集输出：模型回答 `"refactor_tool"` —— 代码一比对就知道**这不在集合里** → 立刻拒绝。

**"合法值有限"直接等价于"非法值可以被机械识别"。** 而能被机械识别的错误，才能被 fail closed 挡住。这就是 A3 那个白名单 else 分支能存在的全部前提。

**② 它给了"我不知道"一个合法出口。**

`unsupported` 本身就是枚举的一个成员。这一点很关键：如果只列 4 个工具，模型面对"今天天气怎样"会被迫在 4 个里挑一个 —— **不是因为它笨，是因为你没给它"都不选"这个选项**。

**把"拒绝"变成集合里的一等公民，模型才能优雅地拒绝。** 这个设计技巧适用于所有分类型的 LLM 应用。

**③ 可以穷举测试。**

5 个值 → 5 条测试用例就覆盖了所有分支，不需要 mock 模型。自由文本输出的分支数是无限的，你没法测。

**④ 模型在闭集上表现更稳。**

"从 5 个里选 1 个"比"生成一段描述"的输出空间小几个数量级，格式漂移的概率随之降低。而且 **API 层可以直接强制**（`response_schema` 的 `enum` 字段，坑 A7 的修法）—— 一旦上了结构化输出，"不在集合里"这件事就从"prompt 里的请求"变成"协议上不可能"。

**⑤ 它让 prompt 变短、变准。**

列 5 个带一句说明的选项，比写三段散文解释"你应该怎么判断"更有效，而且 token 更少。

### 代价 —— 一定要讲这一面

枚举不是免费的：

1. **加一个新工具要改 prompt**（还要改 `TOOL_LABELS`、`CAPABILITIES`、`main()` 的 if 链、前端的 `TOOL_LABELS`……）—— 这就是坑 B4 说的多处真相问题。
2. **闭集之外的合理需求会被硬拒**。用户想要"给我看看这个接口有哪些派生类"（合理、且工具链能做到）→ 落进 `unsupported`。**闭集的边界就是产品的边界。**
3. **枚举只有在代码也校验时才是真约束**。`inject_type` 在 prompt 里是枚举，在代码里不是（坑 B2）—— 结果就是它退化成了一句建议。

**最后一条是 presentation 的一个漂亮转折：枚举约束的力量不来自 prompt，来自下游那个"不认识就拒绝"的判断。prompt 只是提高了命中率，白名单才是那道墙。**

---

## 6. 四个 Prompt 共享的五个套路

把四个 prompt 并排看，会发现同一批手法反复出现。这是 presentation 里最好的"结构化总结"材料。

| # | 套路 | 四处的具体体现 | 要防的行为 |
|---|---|---|---|
| **1** | **闭集优先**（能枚举就不要自由文本） | `tool` 5 选 1、`inject_type` 3 选、状态 `type` 3 选 | 模型自创词汇 |
| **2** | **给模板，不给描述** | 状态机内联整个 Markdown 模板；路由内联 JSON 骨架；注入器逐字段列 schema | 模型"优化"你的格式 |
| **3** | **明确禁止发挥** | `Do not invent restrictions` / `Do not invent unrelated changes` / `guard/action` 仅在暗示时填 / `Never force an unrelated request` | 模型为了"有用"而超出授权 |
| **4** | **只输出产物** | 四处都有 `Output ONLY ...` + `no code fences` | 模型的对话本能（前言、解释、围栏） |
| **5** | **显式缺省值** | `Default inject_type to ["trace"]` / `type` 默认 normal / context 可以只留表头 / `null` 表示"没提到" | 模型在信息不足时**自己发明**一个值 |

**第 3 条和第 5 条是最容易被忽略、又最有价值的两条。**

- 第 3 条防的是 LLM 最根深蒂固的倾向：**帮忙**。而在一个会改写源码的工具里，"多帮一点忙"就是"多改一个文件"。
- 第 5 条的本质是：**信息不足时的行为必须由你规定，不能留给模型**。你不写缺省值，模型不会空着 —— 它会编一个，而且编得很合理、很难发现。

---

## 7. Presentation 讲这一节的建议顺序

1. **先说四次调用都是"翻译/分类"，不是"创作"** → 推出"自由度是成本"这个前提。
2. **拿路由 prompt 当例子讲闭集 + `unsupported` 是一等公民** → 讲 fail closed 的白名单。
3. **拿状态机 prompt 讲"给模板不给描述"** → 顺势讲 `validate()` 的九项语义校验 → 落到"AI 只翻译，正确性由已有工具保证"。
4. **拿接口 prompt 讲"保留风格"** → 展开成"下游消费 diff，所以风格漂移是架构问题不是审美问题"。这是最能体现工程深度的一段。
5. **用"禁止发挥"这条串起三个 prompt** → 承认它**没有代码修法** → 顺势推出 diff 面板和日志摘要的必要性（人在环）。
6. **收尾：prompt 里的规则，只有在代码也检查的时候才是约束。** 拿 `inject_type`（只有 prompt）和状态 `type`（prompt + 白名单 + 中止）做对比 —— 自己代码里的这个不一致，正好是最有说服力的例子。
