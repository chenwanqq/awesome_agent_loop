# todo list,持久化与hook设计模式

在这一章里，我们将像我们的Agent引入todo list，以使其能够在运行过程中追踪需要完成的任务；我们也将要为我们的Agent实现持久化功能，使得当我们退出了我们的CLI功能后，我们能够从储存在文件系统中的运行记录中恢复出之前的状态。

我们先对这两个功能进行一些设计

## todo list

todo list的本质是在Agent执行长期任务的过程中，不断地提示其当前所处的状态，以提高其遵循长期计划的能力。因此，todo list往往与我们之前已实现的Plan模式相互配合。
为了实现todo模式的功能我们需要：

1. 定义一种给Agent看的todo模式的协议
2. 给Agent提供创建、维护todo list的能力
3. 在Agent运行过程中提示当前todo list的状态

### todo模式协议

我们这里使用的是一个json列表的形式
```json
[
        {"task": "任务1", "done": true},
        {"task": "任务2", "done": false}
]
```

或者更严谨的，用json schema的形式来展示，如下：
```json
{
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "任务描述"},
            "done": {"type": "boolean", "description": "是否完成"}
        },
        "required": ["task", "done"]
    }
}
```

### 提供给Agent的InternalTools


针对创建、修改、维护todo list这一点，在过去的工作流设计中，我们可以强制要求我们的LLM应用在初始时产生一个工作流，并在每次执行完工具后，根据工具的执行结果，来更新todo list；然而，随着模型能力的提高，尤其是，agentic training的普及，现有模型的能力完全可以支持另一种模式：即向Agent提供一组工具，这组工具可以创建、维护todo list。

然而，这组工具与之前我们提供的@Tool工具有一个不同，即之前我们提供的工具都是对外部的文件、API进行操作，但是todo工具需要对Agent运行过程中的状态(todo list)进行操作。为此，我们需要：（1）抽象出一组Agent的状态(AgentState)，它包含messages，todo list,current_mode等属性；（2）设计一种新的工具类(InternalTool),它为LLM提供的schema里不包含state这个参数，但实际上却能处理AgentState。

```python
class AgentState(BaseModel):
    """Agent 状态类

    存储对话消息、当前模式、权限覆盖、临时状态、待办事项等
    """
    messages: list[dict] = []
    current_mode: Literal["plan", "default", "auto_edit"] = "default"
    override_authorization: dict[str, Permission] = {}
    tmp_states: dict = {}
    todo_list: list = []

    def clear_state(self):
        """清空状态，重置所有字段"""
        self.messages = []
        self.tmp_states = {}
        self.todo_list = []
```

```python
@internal_tool(default_permission=Permission.ALLOW)
def create_todo(state, tasks: list[dict]) -> str:
    """创建新的待办事项列表，替换当前列表

    Todo列表格式示例：
    [
        {"task": "任务1", "done": true},
        {"task": "任务2", "done": false}
    ]

    Args:
        tasks: 待办事项列表，每项包含 task(描述) 和 done(是否完成)

    Returns:
        操作结果消息
    """
    # 1. 使用 jsonschema.validate 校验 tasks 格式
    validate_todo_list(tasks)

    # 2. 设置 state.todo_list = tasks
    state.todo_list = tasks

    # 3. 返回成功消息
    task_count = len(tasks)
    return f"成功创建待办事项列表，共 {task_count} 项任务"
```

### 提示todo list状态

我们可以在**每次调用LLM前**，向messages列表插入一条user_message，内容是当前的todo list json

## 持久化

我们之前已经定义了一个AgentState,那么自然而然的就会想到，把这个状态类序列化后，储存在文件系统中，以实现持久化功能。在CLI程序中，用--resume xxx来加载之前的运行记录，恢复出之前的状态。但是要在什么时候持久化呢？看起来很多地方都可以放入持久化，例如在LLM调用之前和之后，在工具执行之前和之后……等等地方。结合之前todo list，以及更早的权限控制，它们都是在ReAct Loop中的某个环节插入了一个操作，因此我们可以自然而然得提取出一个概念: Hook。将在某一个地方需要执行的一系列方法抽象为一个hooks列表，在那个位置挨个执行对应的任务就好了
```Hooks
# 1. 执行 pre_user_query_hooks
        for hook in self.pre_user_query_hooks:
            continue_execution, hook_msg = hook(self.state)
            if hook_msg is not None:
                yield hook_msg
            if not continue_execution:
                return
```

最后，我们就可以利用hooks，定义一个add_todo_message(state)的函数，将它加入pre_llm_call_hooks里，在每次调用LLM前，向messages列表插入一条user_message，内容是当前的todo list json

到这一步为止，完整的代码可以参考 `agents/state_cli_agent.py`