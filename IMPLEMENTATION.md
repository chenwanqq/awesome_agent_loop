# 实现细节文档

本文档详细总结了项目中 Tool 系统和 Agent Loop 的代码实现逻辑。

---

## 1. Tool 系统实现

### 1.1 架构概述

Tool 系统采用分层设计，从底层类型解析到高层装饰器，实现完整的工具调用能力：

```
tools/
├── schema.py      # JSON Schema 生成（类型 → Schema）
├── decorator.py   # @tool 装饰器（函数 → Tool 对象）
├── system_tools.py # 系统工具（文件/命令操作）
├── tavily_tools.py # 搜索工具（Tavily 集成）
└── __init__.py    # 模块入口
```

### 1.2 Schema 生成 (`tools/schema.py`)

**核心功能**：从 Python 函数的 type hints 和 docstring 自动生成 OpenAI 格式的工具 Schema。

**关键实现细节**：

| 功能 | 实现方式 |
|------|----------|
| 类型映射 | 使用 `get_type_hints()` 获取类型注解，映射到 JSON Schema 类型 |
| 复杂类型支持 | 支持 `Optional[T]`、`Literal[...]`、`List[T]`、`Dict[K,V]` |
| Docstring 解析 | 解析 Google Style Docstring，提取函数描述和参数描述 |
| Schema 输出 | `get_openai_tool_schema()` 生成完整的 OpenAI Function Calling 格式 |

**类型映射规则**：

```python
str     → {"type": "string"}
int     → {"type": "integer"}
float   → {"type": "number"}
bool    → {"type": "boolean"}
list    → {"type": "array", "items": ...}
dict    → {"type": "object"}
Optional[T] → {"type": "...", "nullable": true}
Literal[...] → {"type": "string", "enum": [...]}
```

**Docstring 解析逻辑**：
- 使用正则表达式识别 `Args:`、`Returns:` 等 section headers
- 提取主描述（Args 之前的部分）
- 解析参数名和描述（支持多行续行）

### 1.3 Tool 装饰器 (`tools/decorator.py`)

**设计模式**：使用包装器模式将普通函数转换为 `Tool` 对象。

**使用示例**：

```python
@tool
def search_weather(location: str, unit: str = "celsius") -> dict:
    """搜索天气
    Args:
        location: 位置
        unit: 单位
    """
    return {"temp": 25}

# 生成的 Tool 对象提供以下属性：
search_weather.openai_schema   # OpenAI 完整格式
search_weather.input_schema    # 输入参数 schema
search_weather.output_schema   # 输出 schema
search_weather(name="Beijing") # 可直接调用
```

**延迟加载机制**：Schema 在首次访问时才生成，避免装饰时的性能开销。

**实现代码**：
```python
class Tool:
    def __init__(self, func: Callable):
        functools.update_wrapper(self, func)
        self.func = func
        self.name = func.__name__
        self._input_schema = None  # 延迟加载
        self._output_schema = None
        self._openai_schema = None

    @property
    def input_schema(self) -> dict:
        if self._input_schema is None:
            self._input_schema = get_input_schema(self.func)
        return self._input_schema
```

### 1.4 内置工具

#### 系统工具 (`system_tools.py`)

| 工具名 | 功能 | 安全机制 |
|--------|------|----------|
| `read_file` | 读取文件内容，支持分页 (`limit`, `offset`) | 路径解析为绝对路径 |
| `write_file` | 创建新文件 | **禁止覆盖已存在文件** |
| `edit_file` | 文本替换编辑 | 精确匹配 `old_text` 后替换 |
| `list_dir` | 列出目录内容 | 标记文件/目录类型 |
| `exec` | 执行 shell 命令 | 超时控制 (默认60s)，输出截断 (10000字符) |

**路径处理**：所有工具使用 `_get_full_path()` 将路径转换为绝对路径，支持 `~` 展开。

#### 搜索工具 (`tavily_tools.py`)

| 工具名 | 功能 | 关键参数 |
|--------|------|----------|
| `tavily_search` | 网络搜索 | `search_depth`: basic/advanced/fast/ultra-fast<br>`topic`: general/news/finance<br>`time_range`: day/week/month/year |
| `tavily_extract` | 网页内容提取 | `extract_depth`: basic/advanced |

**API Key 管理**：从环境变量 `TAVILY_API_KEY` 读取，延迟初始化客户端。

---

## 2. 单轮对话 Agent Loop (`react.py`)

### 2.1 核心流程

单轮对话的 ReAct 循环实现了 **思考 → 行动 → 观察** 的迭代模式：

```
用户输入 → LLM 思考 → 需要工具？
              ↓
         是 ←─┴─→ 否 → 返回最终回答
              ↓
        执行工具调用
              ↓
        将结果加入上下文
              ↓
        继续循环（最多 max_turns 轮）
```

### 2.2 代码实现逻辑

```python
class Agent:
    def __init__(self, model, base_url, api_key, system_prompt, tools):
        self.tools = tools
        self.tool_schema = [tool.openai_schema for tool in tools]
        self.tool_dict = {tool.name: tool for tool in tools}

    def run_single_turn(self, query, max_turns=5):
        messages = [system, user(query)]

        for i in range(max_turns):
            # 最后一轮禁止工具调用，强制输出最终回答
            if i == max_turns - 1:
                messages.append(user("必须根据现有结果生成最终回答"))
                response = completion(..., tool_choice="none")
            else:
                response = completion(..., tool_choice="auto")

            message = response.choices[0].message

            # 情况 1: 没有工具调用，直接返回内容
            if not message.tool_calls:
                return message.content

            # 情况 2: 有工具调用，执行所有工具
            messages.append(assistant_message_with_tool_calls)

            for tool_call in message.tool_calls:
                tool = self.tool_dict[tool_call.function.name]
                result = tool(**json.loads(tool_call.function.arguments))
                messages.append(tool_result_message)

        return message.content
```

### 2.3 关键设计决策

| 设计点 | 实现方式 | 说明 |
|--------|----------|------|
| 工具调用格式 | OpenAI Function Calling | 使用 `tool_choice="auto"` 让模型决定 |
| 多工具处理 | 并行执行 | 一个 LLM 响应可能包含多个 `tool_calls`，全部执行 |
| 消息传递 | 严格遵循 OpenAI 协议 | `assistant` 消息包含 `tool_calls`，`tool` 消息包含结果 |
| 循环终止 | 双重保障 | 1) 无工具调用时终止 2) 达到 max_turns 时强制终止 |
| 最终回答 | 最后一轮禁用工具 | 通过 `tool_choice="none"` 确保输出自然语言 |
| 调试输出 | 三级 verbosity | `none`/`auto`/`debug` 控制输出详细程度 |

### 2.4 消息状态流转示例

```
初始状态:
  [system]: 你是智能助手
  [user]: 搜索最新AI新闻并保存

第1轮 LLM 响应:
  [assistant]: 我来帮你搜索... (tool_calls: [tavily_search])

执行工具后:
  + [tool]: {"results": [...], "answer": "..."}

第2轮 LLM 响应:
  [assistant]: 已找到新闻，现在保存... (tool_calls: [write_file])

执行工具后:
  + [tool]: Successfully created file...

第3轮 LLM 响应:
  [assistant]: 已完成！文件保存在...
  → 无 tool_calls，返回结果
```

### 2.5 工具调用消息格式

**Assistant 消息（包含工具调用）**：
```python
{
    "role": "assistant",
    "content": message.content,
    "tool_calls": message.tool_calls,
    "reasoning_content": message.reasoning_content  # 部分模型支持
}
```

**Tool 消息（工具执行结果）**：
```python
{
    "role": "tool",
    "content": str(result),
    "tool_call_id": tool_call.id,
    "name": tool_name
}
```

### 2.6 错误处理

- **工具不存在**：打印警告，跳过该工具调用
- **工具返回 None**：打印警告，跳过结果添加
- **工具执行异常**：由具体工具内部捕获，返回错误字符串

---

## 3. 扩展指南

### 3.1 添加新工具

1. 创建函数并添加 `@tool` 装饰器
2. 编写 Google Style Docstring（包含 Args 和 Returns）
3. 添加类型注解
4. 在 `tools/__init__.py` 中导出

```python
from tools import tool

@tool
def my_tool(param: str) -> dict:
    """工具描述
    Args:
        param: 参数描述
    Returns:
        返回值描述
    """
    return {"result": param}
```

### 3.2 使用 Agent

```python
from react import Agent
from tools import tavily_search, read_file

agent = Agent(
    model="openai/gpt-4",
    base_url="...",
    api_key="...",
    system_prompt="你是智能助手",
    tools=[tavily_search, read_file]
)

result = agent.run_single_turn("你的问题", max_turns=5, verbose="auto")
```
