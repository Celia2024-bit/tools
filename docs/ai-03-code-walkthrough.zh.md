# AI 相关代码逐段讲解

> 面向 presentation 的第 3 份文档。目标是**你能像自己写的一样讲出每一段代码在干什么、为什么这么写、出错时会怎么走。**
>
> 读法建议：每一节先看"一句话职责"，再看代码，再看"为什么"。§8 的异常传播表和 §9 的耦合清单是最容易被追问的两块，建议单独记。

---

## 0. 文件地图：哪些文件属于"AI 层"

```
tools/
├── nl_dev_tool.py                       ← 【核心】路由器 + 调度器，CLI 和 Web 共用同一份
├── server.py                            ← 【核心】Flask API：跑子进程、做快照 diff、抓 marker
├── site/ai/index.html                   ← 【核心】浏览器控制台（单文件，无构建）
│
├── state_machine/nl_to_state_machine.py ← 生成器①：一句话 → 状态机 Markdown
├── aspect_injector/nl_to_aspect_config.py ← 生成器②：一句话 → config.json
├── sync_interface/nl_to_new_interface.py  ← 生成器③：旧头文件 + 一句话 → 新头文件
│
└── （以下是原有的确定性工具，AI 层一行都没改过它们）
    aspect_injector/aspect_injector.py
    sync_interface/interface_sync.py
    state_machine/table_to_json.py, json_to_cpp.py, json_to_mermaid.py
```

**这个分层本身就是第一个要讲的点：AI 层是 6 个新文件，下面那些原有工具一行都没动。** 这是"只在前面加一道门"的架构，而不是"把 AI 织进现有代码"。它的直接好处是：AI 层整个删掉，所有工具照常工作。

---

## 1. `nl_dev_tool.py` 的开头：路径与常量

### 1.1 为什么要手动改 `sys.path`

```python
TOOLS_DIR = Path(__file__).resolve().parent
STATE_MACHINE_DIR  = TOOLS_DIR / "state_machine"
SYNC_INTERFACE_DIR = TOOLS_DIR / "sync_interface"
ASPECT_INJECTOR_DIR = TOOLS_DIR / "aspect_injector"

for path in [TOOLS_DIR, STATE_MACHINE_DIR, SYNC_INTERFACE_DIR, ASPECT_INJECTOR_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
```

**一句话职责：** 让 `from nl_to_state_machine import ...` 这种裸 import 能work，尽管那些文件在子目录里。

**为什么这么写：** 三个工具目录各自是独立的、没有 `__init__.py` 的脚本集合（它们本来是三个独立项目）。要么把它们改造成包（动老代码），要么在入口处把目录塞进 `sys.path`（不动老代码）。**这里选了后者 —— 又一次"不碰已有工具"。**

**代价（值得知道，可能被问）：** `sys.path` 污染是全局的，如果两个工具目录里有同名模块（比如 `sync_interface/logger.py` 和 `aspect_injector/aspect_injector_pkg/logger.py`），谁在前面谁赢。目前不冲突是因为后者在包里。

**`Path(__file__).resolve().parent` 而不是 `Path.cwd()`：** 因为脚本可能从任何目录被调用（server.py 就是从别处调的）。**"位置感"必须来自文件自身，不能来自调用者的 cwd。**

### 1.2 三个常量表各自的用途

```python
TOOL_LABELS = {          # 机器名 → 人类可读名。日志和前端摘要用
    "state_machine": "State Machine Generator",
    ...
    "unsupported": "Out of scope",
}

PERF_DASHBOARD_URL = "https://tools-lime-eight.vercel.app/"    # 性能监控的"全部答案"

CAPABILITIES = [         # (工具名, 能做什么, 示例请求) —— 被拒绝时打印给用户看
    ("state_machine", "generate a C++ state machine ...", "An order system that ..."),
    ...
]
```

**`CAPABILITIES` 这个表是一个容易被低估的设计。** 它的唯一用途是在请求被拒绝时告诉用户"我能做什么、请求长什么样"：

```python
def handle_unsupported(description, reason):
    detail(f"reason: {reason or 'the request does not match any of the tools'}")
    print("\nNo tool was run, so nothing was generated or modified.")
    print_capabilities()                       # ← 这里
    print("\nRephrase the request in terms of one of the tasks above and try again.")
```

**为什么重要：** 一个会拒绝的系统，如果只说"不支持"，用户唯一的策略就是瞎试。**拒绝必须附带"正确的样子"** —— 每条能力还带了一个示例句子，用户可以直接照着改。这是"拒绝路径也要有产品设计"的体现，presentation 里值得提一句。

### 1.3 退出码常量

```python
EXIT_UNSUPPORTED = 2
EXIT_ROUTER_UNAVAILABLE = 3
```

**为什么要专门定义：** 因为 `server.py` 要靠退出码区分三种完全不同的情况，而它只能看到子进程的返回码。0/2/3/其他 这四档的设计见 §8。

**核心思想："我拒绝"不是"我崩了"。** 一个进程只有 `0 = 成功` 和 `非 0 = 失败` 两档的时候，"out of scope"就只能被表达成失败 —— 而那是错的，因为它是一个**正常的、正确的**结果。

---

## 2. 进度打印函数：它们是协议，不是日志

```python
STEP_TOTAL = 3

def banner(title):   print(f"\n{'='*62}\n  {title}\n{'='*62}", flush=True)
def step(i, msg):    print(f"\n[{i}/{STEP_TOTAL}] {msg}", flush=True)
def detail(msg):     print(f"      -> {msg}", flush=True)
def bullet(msg):     print(f"         {msg}", flush=True)

def report_artifact(label, path):
    detail(f"artifact [{label}]: {rel_to_tools(path)}")
```

代码里那段注释把它讲得很清楚：

```python
# The web dashboard pipes this stdout straight into its log panel and also
# scrapes a few markers out of it, so keep these line shapes stable:
#   "-> AI selected tool: <tool>"
#   "-> artifact [<label>]: <path>"     (the path is always last on the line)
#   "-> dashboard: <url>"               (performance monitor: the whole answer)
# Plain ASCII only: this output gets captured by consoles that are not UTF-8.
```

**要讲的三点：**

**① 这四行的格式是一份接口契约。** `server.py` 里有四个正则去抓它们：

```python
TOOL_MARKER      = re.compile(r"AI selected tool:\s*([a-z_]+)")
ARTIFACT_MARKER  = re.compile(r"artifact \[[^\]]*\]:\s*(.+?)\s*$", re.MULTILINE)
REASON_MARKER    = re.compile(r"^\s*->\s*reason:\s*(.+?)\s*$", re.MULTILINE)
DASHBOARD_MARKER = re.compile(r"^\s*->\s*dashboard:\s*(\S+)\s*$", re.MULTILINE)
```

改掉打印格式 → **CLI 一切照常，网页悄悄坏掉**。这是最难查的一类 bug，所以两个文件里都写了注释互相指认。

**② "路径永远放在行尾"是刻意的。** 因为 `artifact [...]: (.+?)$` 这个正则要贪心地吃到行尾。如果写成 `artifact [spec]: path/to/x.md (12 lines)`，正则就会把 `(12 lines)` 也吃进路径里。**设计输出格式的时候就考虑了怎么被解析** —— 这是"为下游着想"的一个具体例子。

**③ 为什么强制纯 ASCII。** 这行注释背后是真实的踩坑：Windows 控制台默认不是 UTF-8，输出一个 emoji 可能直接抛 `UnicodeEncodeError` 让整个运行崩掉。对应的另一半防御在 `server.py`：

```python
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
```

**注意这里其实有个不一致值得你知道：** `nl_to_state_machine.py` 的 `run_pipeline()` 里是有 emoji 的（`🔨 Compiling`、`🚀 Running`）。之所以没炸，是因为 server 强制了 UTF-8 环境变量。所以那条"纯 ASCII"纪律在主路径上守住了，在子流水线里没有 —— 依赖的是环境变量这道保险。被问到"你怎么知道"，这就是一个很好的"我读过自己代码"的证据。

---

## 3. `route_intent()` —— 整个 AI 层的入口，逐行

```python
def route_intent(description: str) -> dict:
    """Use Gemini to quickly determine which sub-tool to invoke, with auto-retry for 429."""
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        started = time.time()
        try:
            response = client.models.generate_content(
                model=ROUTER_MODEL,                       # gemini-3.6-flash
                contents=description,                     # ① 用户原话
                config=types.GenerateContentConfig(
                    system_instruction=ROUTER_SYSTEM_PROMPT,   # ② 规则
                    max_output_tokens=200,                     # ③ 预算
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True),                         # ④ 不给它调工具
                ),
            )
            text = response.text.strip()
            if text.startswith("```"):                  # ⑤ 剥围栏
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            intent = json.loads(text.strip())           # ⑥ 这就是"检查是不是 JSON"
            detail(f"Gemini answered in {time.time() - started:.1f}s")
            return intent

        except errors.ClientError as e:
            if e.code == 429 and attempt < max_retries - 1:
                detail(f"Gemini rate limit (429), retrying in {retry_delay}s "
                       f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2                        # ⑦ 指数退避
            else:
                raise e
```

### 逐点解释

**① `contents=description` vs ② `system_instruction=...`：职责分离。**
用户的话放 `contents`（数据），规则放 `system_instruction`（指令）。这不只是整洁 —— 模型对 system instruction 的遵循度更高，而且**这是防 prompt 注入的基本姿势**：指令和数据分开通道。

**③ `max_output_tokens=200`：** 输出只有 4 个短字段。给紧一点是为了省延迟和钱（路由是每次都跑的一步）。代价见坑 A2/A4 —— 撞上 MAX_TOKENS 时 `response.text` 可能是 `None`，而**这里没有 `if not response.text` 检查**（三个生成器都有，唯独这里漏了）。

**④ `automatic_function_calling(disable=True)`：** 我们没给模型任何可调用的工具。禁掉可以确保这次调用**严格是"一问一答"**，不会被 SDK 自动展开成多轮。可预测性优先。

**⑤ 剥 markdown 围栏：** prompt 里已经写了 `Do not wrap in markdown code fences`，这里又剥了一次 —— **这是刻意的双保险**。presentation 可以直接用这句话：

> prompt 里的规则是"请求"，代码里的处理才是"保证"。凡是能在代码里廉价兜住的，就不要只依赖模型听话。

`split("```")[1]` 的原理：`"```json\n{...}"` 按 ``` 切开得到 `['', 'json\n{...}']`，取 index 1 就是内容；再判断开头是不是 `json` 把语言标签切掉 4 个字符。

**⑥ `json.loads` 就是"格式校验"本身。** 注意它**只校验语法，不校验语义** —— `{"tool": "delete_everything"}` 是合法 JSON，能通过这里。语义校验（tool 必须在 5 个里）发生在 `main()`。**两层校验分在两个地方，这点被问到要能答上来。**

**⑦ 指数退避：** 5s → 10s。为什么不固定 5s：如果是短时突发限流，第一次重试就好了；如果是配额耗尽，等更久也没用，**快速失败比死等好**。3 次上限 = 总共最多等 15 秒，不会让一个网页请求挂太久。

### 这个函数的异常出口（很容易被追问）

| 异常 | 来源 | 在这里被处理吗 | 最终结果 |
|---|---|---|---|
| `ClientError(429)` | 限流 | ✅ 重试最多 3 次 | 成功，或最后一次抛出 |
| 其他 `ClientError` / `APIError` | 401 无效 key、服务不可用 | ❌ 直接 `raise` | `main()` 捕获 → 打印一行说明 → **exit 3** |
| `json.JSONDecodeError` | 模型输出不是 JSON | ❌ **没有捕获** | 一路抛到顶 → **traceback，exit 1** → 前端 `error (exit 1)` |
| `AttributeError` | `response.text` 是 `None` | ❌ **没有捕获** | 同上 |

**后两行就是坑 A1/A2。** 方向是对的（绝不把垃圾往下游传），但表现是"崩了"而不是"它拒绝了"。修法见坑文档。

**还有一个隐藏的第五种情况：** 如果 `for` 循环跑完既没 `return` 也没 `raise`（理论上现在不会发生，因为最后一次 attempt 走 `else: raise`），函数会**隐式返回 `None`** → `main()` 里 `intent.get("tool")` 抛 `AttributeError`。这是"函数有一条没有显式返回值的路径"的经典味道，加一行 `raise RuntimeError("unreachable")` 收口会更干净。这种细节被面试官问到时能主动指出来，比被指出来好。

---

## 4. `resolve_path()` —— 最短、也最危险的函数

```python
def resolve_path(path_str: str, default_path: Path = None) -> Path:
    if not path_str:
        return default_path.resolve() if default_path else None

    p = Path(path_str)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()      # ① 相对路径按"调用时的 cwd"解析
    else:
        p = p.resolve()

    if not p.exists() and default_path and default_path.exists():
        return default_path.resolve()       # ② 不存在就静默回退 ←←← 危险
    return p
```

**一句话职责：** 把三种来源的路径（AI 抽取的、命令行给的、什么都没给）统一成一个绝对路径。

**① 为什么按 `Path.cwd()` 解析：** 让用户能像在终端里一样写相对路径。服务端调用时 `cwd` 被固定成 `TOOLS_DIR`（`server.py` 里 `cwd=TOOLS_DIR`），所以 `sync_interface/test/src` 这种写法在网页上也成立。

**② 第二段是坑 B1 的根源，必须能讲清楚：**

它把两件完全不同的事当成了同一件事处理：

| 情况 | 应该怎么办 | 现在怎么办 |
|---|---|---|
| 用户根本没提路径 | 用默认值 ✅ 合理 | 用默认值 |
| **AI 把路径抽错了**（`"folder src"`） | **应该报错** | **静默用默认值** ❌ |

于是：你想同步 `my_project/src`，AI 抽成了 `folder src` → 代码不吭声，去改了 `sync_interface/test/src` → 前端显示 success + 漂亮的 diff。**你以为成了，其实目标目录一个字没动，另一个目录被改了。**

对比同一个函数的两个调用点，处理还不一样：

```python
old_path = resolve_path(raw_old)
if not old_path or not old_path.is_file():
    print(f"Error: Old header file not found at: {old_path}", file=sys.stderr)
    sys.exit(1)                              # ✅ old_header 错了 → 响亮失败

src_dir = resolve_path(raw_src, default_src) # ❌ src_dir 错了 → 静默回退
```

**同一个函数、同一次调用里的两个参数，一个会喊、一个不会。** 这个对比放在 presentation 里非常有冲击力，而且修法只要两行（回退时打一条 WARNING，或者干脆区分"没提"和"提错了"）。

---

## 5. 三个 `summarize_*()` —— 让 AI 的决策留痕

```python
def summarize_state_machine_spec(md_text):   # 从生成的 Markdown 里反解出状态/事件/context
def summarize_header_rewrite(old, new):      # 对新旧头文件做 unified_diff，打印 ± 行
def summarize_aspect_config(config_data):    # 把每条 inject/remove/exclude 规则打印出来
```

**一句话职责：** 把"模型做了什么决定"翻译成人能扫一眼的日志。

它们**对功能毫无贡献** —— 删掉，所有工具照常工作。但它们是 presentation 里必须讲的一块，理由有三个：

**① 它们是坑 B3（AI 自行增删限制）的唯一防线之一。** 模型偷偷加了一条 exclude，代码没法知道，但 `summarize_aspect_config()` 会把它打印出来：

```
-> AI produced 1 inject rule(s)
   - dir=test/src  types=[trace, validate]
-> AI produced 1 exclude rule(s)
   - dir=test/src  file=AlphaEngine.cpp
```

你扫一眼就能发现"咦，我没说要排除这个"。

**② demo 说服力。** 没有它们，日志就只是"调用了 API、写了文件、跑了子进程"，观众看不到 AI 到底干了什么。有了它们，日志会说：

```
-> AI designed 3 states: Pending, Paid, Completed
-> AI designed 2 transitions on events: PaymentReceived, OrderDelivered
-> AI rewrote the interface: +4 / -2 lines
```

**这是"可解释性"最廉价的实现方式** —— 不需要任何 AI 技术，就是把中间产物解析一遍打出来。

**③ `summarize_state_machine_spec()` 里有一个细节值得讲：** 它自己包了 try/except：

```python
except Exception as e:
    detail(f"could not summarize the generated spec: {e}")
    return
```

**为什么：因为它是"锦上添花"的功能，绝不能让它弄坏主流程。** 摘要失败只是少打几行日志，状态机照样生成。这条原则叫"可观测性代码不能影响被观测的行为" —— 一行 try/except 就体现出来了，很适合当细节亮点讲。

---

## 6. 三个 handler：统一的三段式

三个 handler 长得不一样，但骨架完全相同 —— **这是"设计哲学落地"最直接的证据**：

```
第 1 段：确定产物写到哪（resolve_path + 默认路径）
第 2 段：调 Gemini 生成产物 → 落盘 → report_artifact() → summarize_*()
第 3 段：if not should_run: return          ← --no-run 在这里生效
         subprocess.run([...], check=True) ← 交给原有的确定性工具
```

以 `handle_aspect_injector()` 为例，它比另外两个多了一步，而这一步很有讲头：

```python
config_str = nl_to_config_json(description)          # 生成
config_data = json.loads(config_str)

def clean_dir(target_list):
    for item in target_list:
        d = item.get("directory", "")
        if d:
            p = Path(d); parts = p.parts
            if parts and parts[0] == "aspect_injector":   # ① 剥掉模型爱加的仓库前缀
                d = str(Path(*parts[1:]))
            abs_dir = (ASPECT_INJECTOR_DIR / d).resolve()
            if abs_dir.exists():
                item["directory"] = str(abs_dir)          # ② 绝对化，cwd 再也不影响结果
            else:
                item["directory"] = d                     # ③ 不存在 → 原样保留 ←危险
```

**① 为什么要剥 `aspect_injector/` 前缀：** 用户在网页上会写 `aspect_injector/test/src`（这是从仓库根看的路径），但注入器的工作目录是 `aspect_injector/` 本身，它期望的是 `test/src`。**模型忠实地照用户的话抽了路径，但两者的参照系不同。**

这是一个特别好的 presentation 点：**prompt 管不住的东西，用代码兜。** 你可以在 prompt 里反复强调"路径要相对于 aspect_injector 目录"，但用户输入的原话里就带着前缀，模型照抄是合理行为。与其和模型较劲，不如在代码里做一次**幂等的规范化** —— 有前缀就剥掉，没有就不动。

**② 绝对化的价值：** 之后不管子进程的 cwd 是什么，路径都指向同一个地方。这类"尽早把相对量变成绝对量"的处理能消灭一整类 bug。

**③ 但 else 分支又是一个静默回退**（坑 B1 的孪生兄弟）：目录不存在就原样传给注入器 → `find_cpp_files()` 里 `Path(不存在的目录).rglob("*.cpp")` **返回空列表且不抛异常** → `files_scanned: 0` → `cli.py` 照样 `return 0` → 前端 **success，Changed files: 0**。

**记住这条链路，它是 presentation 里最有说服力的"静默失败"演示：从一个错误的路径字符串，到一个显示"成功"的绿色徽章，中间没有任何一环会报错。**

---

## 7. `main()` 的控制流

```python
def main():
    args = parser.parse_args()
    should_run = not args.no_run

    banner("AI C++ DEV ASSISTANT")
    print(f"  request : {args.description}")
    print(f"  mode    : {'generate + run' if should_run else 'generate only (--no-run)'}")

    step(1, f"Asking Gemini ({ROUTER_MODEL}) which tool this request needs...")
    try:
        intent = route_intent(args.description)
    except errors.APIError as e:                       # ① 只接 API 层错误
        message = getattr(e, "message", None) or str(e)
        print(f"\nThe Gemini router is unavailable: {getattr(e, 'code', '?')} {message}",
              file=sys.stderr)
        print("Nothing was generated or modified. Try again later.", file=sys.stderr)
        sys.exit(EXIT_ROUTER_UNAVAILABLE)              # ② 专属退出码

    tool = intent.get("tool")
    detail(f"AI selected tool: {tool}  ({TOOL_LABELS.get(tool, 'unknown tool')})")   # ③ marker
    detail(f"AI extracted hints: old_header={...}, src_dir={...}")                   # ④ 透明

    if   tool == "state_machine":       handle_state_machine(...)
    elif tool == "interface_sync":      handle_interface_sync(...)
    elif tool == "aspect_injector":     handle_aspect_injector(...)
    elif tool == "performance_monitor": handle_performance_monitor(...)
    else:                                              # ⑤ 白名单的"墙"
        handle_unsupported(args.description, intent.get("reason"))
        banner("OUT OF SCOPE - no tool was run")
        sys.exit(EXIT_UNSUPPORTED)

    banner(f"COMPLETED - {TOOL_LABELS.get(tool, tool)}")
```

**① 为什么只捕 `errors.APIError`：** 想区分"外部服务的问题"和"我们自己的 bug"。API 错误是可预期的运维状况（配额、网络、key）→ 给一句人话 + 专属退出码。我们自己的 bug 就该让 traceback 出来。**思路是对的，只是分类漏了 `JSONDecodeError`（坑 A1）—— 它既不是 API 错误也不是我们的 bug，是"模型不听话"，应该有第三类处理。**

**② `sys.exit(EXIT_ROUTER_UNAVAILABLE)` 之前那句 `"Nothing was generated or modified."`：** 出错时最重要的信息不是"哪里错了"，而是**"系统现在处于什么状态"**。用户真正想知道的是"我的文件动了没有"。这句话直接回答了。

**③ 这一行是 marker：** `detail()` 会输出 `      -> AI selected tool: aspect_injector  (Aspect Injector)`，`server.py` 的 `TOOL_MARKER` 正则从中抓出 `aspect_injector`。注意正则是 `([a-z_]+)` —— 只认小写和下划线，所以如果模型返回 `"Aspect_Injector"`，marker 抓不到（不过那种情况已经落进 else 被拒了，所以无害）。

**④ 把抽取到的 hints 打出来：** 这一行就是坑 B1 的"检测手段"。路径抽错了，日志里看得见 —— 前提是有人看。

**⑤ 这个 `else` 就是 §A3 讲的那道墙。** 再强调一遍它的性质：**代码问的是"是不是我认识的四个之一"，不是"是不是 unsupported"。** 所以任何意外值（拼错、大小写、null、数组、新词）都会落进来。这是整个 AI 层最重要的五行代码。

---

## 8. 异常传播总表（最容易被追问，建议背下来）

| 发生了什么 | 在哪抛/判断 | 谁捕获 | 退出码 | server 的 `status` | 前端显示 |
|---|---|---|---|---|---|
| 一切正常 | — | — | 0 | `success` | 绿色 success + diff |
| 请求 out of scope | 模型返回 `unsupported` | `main()` 的 else | **2** | `unsupported` | 琥珀色"out of scope — nothing ran"，Changed files: 0 |
| 模型返回了未知 tool 名 | `main()` 的 else | 同上 | **2** | `unsupported` | 同上 |
| 配额耗尽 / key 无效 / 服务挂了 | `route_intent()` 抛 `APIError` | `main()` 的 except | **3** | `router_unavailable` | 琥珀色"AI router unavailable" |
| 429 限流（可恢复） | `route_intent()` | 自己重试 3 次 | 通常 0 | `success` | 正常，日志里有重试记录 |
| **模型输出不是 JSON** | `json.loads` | **没人** | 1 | `error` | 红色 `error (exit 1)` + traceback |
| **`response.text` 是 None** | `.strip()` | **没人** | 1 | `error` | 同上 |
| 旧头文件路径不存在 | `handle_interface_sync()` | 自己 `sys.exit(1)` | 1 | `error` | 红色，但日志里有清楚的一行说明 |
| 状态机语义校验不通过 | `table_to_json.py` 的 `validate()` → `sys.exit(1)` | `subprocess(check=True)` 抛 `CalledProcessError` | 1 | `error` | 红色，日志里列出每一条 error |
| 生成的 C++ 编译失败 | `g++` 非零 | 同上 | 1 | `error` | 红色 + 编译器输出 |
| **src_dir 抽错了** | 无人判断 | — | **0** | **`success`** | **绿色 success —— 但改的是别的目录** |
| **directory 不存在（注入器）** | 无人判断 | — | **0** | **`success`** | **绿色 success，Changed files: 0** |

**最后两行加粗的部分，就是整份坑文档想说的全部。** 这张表做成一页 slide，是 presentation 里信息密度最高的一张。

---

## 9. `server.py`：AI 层的"可见性"都在这里

### 9.1 核心机制：前后快照做 diff

```python
WATCH_DIRS = ["aspect_injector/test", "sync_interface/test"]

watch_dirs = _resolve_dirs(WATCH_DIRS)
before = _snapshot(watch_dirs)        # ① 运行前：{相对路径: 全文}
res = subprocess.run(cmd, ...)        # ② 跑子进程
after = _snapshot(watch_dirs)         # ③ 运行后
diffs = _build_diffs(before, after)   # ④ difflib.unified_diff 逐文件
```

**为什么用快照而不是 `git diff`：** 快照对**未提交、未跟踪**的状态一律有效，不依赖 git 状态是否干净，也不受上一次运行残留的影响（因为对比的是"这次运行前后"，不是"和 HEAD 比"）。代价是要把文件全文读进内存两遍 —— 所以有 `TEXT_SUFFIXES` 白名单和 `MAX_FILE_BYTES = 256 KiB` 上限。

**代码注释里那句话点明了动机：**

```python
# The AI router picks the sub-tool inside the child process, so we snapshot every
# directory the tools may rewrite and diff whatever actually changed.
```

**关键洞察：服务端不知道 AI 会选哪个工具，所以它不能"预测"哪些文件会变 —— 只能全部盯着，然后看实际变了什么。** 这是"用观测代替预测"的设计，很适合讲：

> 我没有让 server 去理解每个工具会改什么。它只做一件事：运行前拍一张照，运行后再拍一张，把差异算出来。工具再多，这段代码都不用改。

**已知边界：** 只盯 `WATCH_DIRS` 两个目录（坑 C4）；两次运行并发会互相串味（坑 C3）—— 因为"运行期间的所有变化"都会被算进这一次的 diff。

### 9.2 状态码映射

```python
if res.returncode == 0:
    status = "success"
elif res.returncode == EXIT_UNSUPPORTED or tool_detected == "unsupported":
    status = "unsupported"          # ← 双条件，冗余保险
elif res.returncode == EXIT_ROUTER_UNAVAILABLE:
    status = "router_unavailable"
else:
    status = "error"
```

注意第二个分支的 `or` —— 退出码和 marker **两个独立信号**都能判定 unsupported。这是刻意的冗余：万一将来有人改了退出码忘了改这里，marker 还能兜住。

### 9.3 artifact 收集，和一个要注意的行为

```python
ARTIFACT_DIRS = {"state_machine": ["state_machine/out", "state_machine/output"]}

artifact_dirs = _resolve_dirs(ARTIFACT_DIRS.get(tool_detected, []))
reported = _artifact_paths_from_logs(logs)        # 从 marker 抓的
response_data["artifacts"] = _collect_artifacts(artifact_dirs, reported)
```

两个来源：**日志里报告的**（精确，就是这次生成的）+ **整个输出目录**（宽泛，可能含旧文件）。

**这里有个值得知道的行为：`out/` 目录里如果有上次运行留下的产物，这次也会被一起显示。** 代码在 mermaid 那里专门处理了这个问题：

```python
if tool_detected == "state_machine":
    out_dir = TOOLS_DIR / "state_machine" / "out"
    # 按这次报告的 .md 名字去找对应的 .mmd —— out/ 里可能还有旧图
    candidates = [out_dir / f"{p.stem}.mmd" for p in reported if p.suffix.lower() == ".md"]
    candidates.append(out_dir / "state_machine.mmd")
```

注释写得很直白：*"the out/ directory can still hold older diagrams"*，**给今天的请求显示昨天的图，比不显示图更糟。** 但 artifacts 列表本身没有做同样的过滤 —— 所以图是准的，文件列表可能混入旧产物。这是一个真实的小不一致，主动指出来是加分项。

### 9.4 子进程调用的四个细节

```python
cmd = [sys.executable, "nl_dev_tool.py", prompt]     # ① list 形式
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")   # ② 强制 UTF-8
res = subprocess.run(cmd, capture_output=True, text=True,
                     encoding="utf-8", errors="replace",           # ③ 坏字节不崩
                     env=env, cwd=TOOLS_DIR)                       # ④ 固定 cwd
```

**① `sys.executable` 而不是 `"python3"`：** 注释写了理由 —— 裸 `python3` 可能解析到另一个 Python 安装（没装依赖的那个）。**"用当前解释器"是唯一可靠的写法。**

**① list 形式 + 默认 `shell=False`：** 这是**整个服务最重要的一处安全决策**。用户 prompt 里写 `"; rm -rf / #"` 只会被当成一个普通字符串参数，不经过 shell。如果这里写成 `subprocess.run(f"python nl_dev_tool.py '{prompt}'", shell=True)`，整个服务立刻变成远程命令执行漏洞。**同样的功能，一个参数的差别。**

**③ `errors="replace"`：** 子进程吐出无法解码的字节时，用替换字符代替而不是抛异常。**日志读取绝不能因为一个坏字节把整个响应搞没了。**

**没做的事（坑 C1）：** 没有 `timeout=`。状态机链路最后会**运行生成的二进制**，一个死循环就能让这个请求永久挂住。

### 9.5 `/reset`

```python
tracked, untracked, _ = _porcelain_status()   # ① 先看现状
restore = _git("restore", ".")               # ② 丢弃所有已跟踪文件的修改
after_tracked, _, _ = _porcelain_status()    # ③ 再看一次，确认真的干净了
```

三步的意义：**做危险操作前后都取一次状态，这样报告里能说清"恢复了哪 5 个文件、留下了哪 3 个未跟踪文件、还有哪几个居然没恢复成功"。** 未跟踪文件（生成的产物、日志）被刻意留着不动 —— 只回滚"对已有代码的修改"，不删"新生成的东西"。

**存在的理由（注释里写了）：** 注入器和 interface_sync **原地改写自己的测试源码**，长期运行的容器里第二次运行就不再从提交基线出发了。一个悄悄把改动叠在改动上的 demo，会越跑越不可信。

---

## 10. 前端 `runTool()` 的流程

```js
runBtn.disabled = true;                    // ① 防重复提交
logElement.innerText = `[INFO] Sending request to the AI router...`;
setDiagramVisible(false); showDashboard(null);      // ② 先清空上一次的一切
lastArtifacts = []; lastDiffs = [];
renderArtifacts(); renderDiffs();

const response = await fetch(API_URL, {method:'POST', body: JSON.stringify({prompt})});
const data = await response.json();

logElement.innerText = data.logs || JSON.stringify(data, null, 2);   // ③ 日志优先
lastArtifacts = data.artifacts || []; lastDiffs = data.diffs || [];
renderSummary(data); renderArtifacts(); renderDiffs();
showDashboard(data.dashboard);
if (data.mermaid) { ...渲染图... }                                   // ④ 有图才显示
```

**② 为什么每次都先彻底清空：** 否则上一次运行的 diff / 图 / 产物会留在页面上，用户以为是这一次的结果。**"陈旧的正确信息"比"没有信息"更危险** —— 和 §9.3 里 mermaid 那个处理是同一个原则。

**③ `data.logs ||` 后面的 fallback：** 万一后端 500 了没有 logs 字段，就把整个响应 JSON 打出来。**永远给用户一些东西看，不要留一片空白。**

**④ 图表面板的动态布局：**

```js
function setDiagramVisible(visible) {
    document.getElementById('diagram-panel').style.display = visible ? 'flex' : 'none';
    document.getElementById('main-grid').className = visible
        ? 'grid grid-cols-1 lg:grid-cols-2 gap-6'
        : 'grid grid-cols-1 gap-6';          // ← 没有图时日志占满整宽
}
```

只有状态机会产图。其他三个工具（和被拒绝的请求）如果留着一个空面板，就是白占一半屏幕。**没有内容的面板不该存在，而不是该显示"暂无数据"。**

**一个 bug（坑 C5）：** `innerHTML` 拼接了模型生成的 mermaid 内容，没有转义 —— 同一个文件里日志用 `innerText`、artifact 用 `esc()`，只有这里漏了。**AI 生成的内容对前端来说是不可信输入，和用户输入同级。**

---

## 11. "加一个第 5 个工具，要改几个地方？"

这个问题presentation 上很可能被问（或者你主动提，效果更好）。答案是 **10 处，横跨 3 种语言**：

| # | 文件 | 改什么 |
|---|---|---|
| 1 | `nl_dev_tool.py` | `TOOL_LABELS` 加一项 |
| 2 | `nl_dev_tool.py` | `CAPABILITIES` 加一项（含示例句） |
| 3 | `nl_dev_tool.py` | `ROUTER_SYSTEM_PROMPT` 的选项列表 |
| 4 | `nl_dev_tool.py` | `ROUTER_SYSTEM_PROMPT` 里 JSON 格式那段的 enum 值 |
| 5 | `nl_dev_tool.py` | `main()` 的 if/elif 链加一支 |
| 6 | `nl_dev_tool.py` | 新写一个 `handle_xxx()` |
| 7 | 新文件 | `nl_to_xxx.py`（生成器 + 它的 system prompt） |
| 8 | `server.py` | `DEFAULT_PROMPTS`、必要时 `WATCH_DIRS` / `ARTIFACT_DIRS` |
| 9 | `site/ai/index.html` | `PRESETS`、`TOOL_LABELS`、预设按钮的 HTML |
| 10 | `site/*.html` | 文档页 |

**这个清单本身就是一个论点：** 5 个工具的时候还行，15 个就不行了。**这是"枚举 + 白名单"设计的真实代价 —— 安全性换来的是耦合。**

值得一起讲的改进方向（说明你知道下一步该往哪走，但也知道现在不做是对的）：

- 把 **tool 注册表**做成单一数据结构（名字、标签、能力描述、示例、handler、watch dirs 全在一处），prompt 的选项列表和前端的按钮都从它生成 → 第 1、2、3、4、8、9 项合成 1 项
- 前端通过 `GET /tools` 拿这张表 → 跨语言的那道重复也断了
- **但现在不做是对的**：4 个工具的时候，注册表的抽象成本高于它省下的维护成本。**知道什么时候不抽象，和知道怎么抽象一样重要。**

---

## 12. 自测清单：能不看代码答出这些，就算真的熟了

1. 一次运行调用了几次 Gemini？分别在哪个文件、干什么？
2. 模型返回 `"tool": "aspect"`（拼不全）会发生什么？走到哪一行？退出码？
3. 模型返回的不是 JSON 会发生什么？和上一问的处理**有什么本质区别**？
4. 退出码 2 和 3 分别代表什么？为什么要区分？
5. `server.py` 怎么知道 AI 选了哪个工具？（提示：不是靠返回值）
6. diff 是怎么算出来的？为什么不用 `git diff`？
7. 用户说 `"in the folder src"`，AI 抽成 `"folder src"`，最终会改哪个目录？前端显示什么颜色？
8. 为什么 prompt 里写了"不要加代码围栏"，代码里还要再剥一次？
9. `--no-run` 在三个 handler 里各自阻止了什么？
10. 为什么 `summarize_state_machine_spec()` 自己包了 try/except？
11. 为什么 `subprocess.run` 用 list 而不是字符串？不这么写会怎样？
12. 加第 5 个工具要改几个地方？为什么这么多？

**答不上来的那几条，就是你在 presentation 上最可能被问倒的地方 —— 先补那几条。**
