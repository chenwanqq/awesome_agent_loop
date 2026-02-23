# Todo List, Persistence, and Hook Design Pattern

In this chapter, we will introduce a todo list to our Agent so it can track tasks to be completed during execution. We will also implement persistence functionality for our Agent, allowing us to restore the previous state from records stored in the file system after exiting our CLI.

Let's first do some design for these two features.

## Todo List

The essence of a todo list is to continuously prompt the Agent of its current status during the execution of long-term tasks, to improve its ability to follow long-term plans. Therefore, the todo list often works in conjunction with the Plan mode we previously implemented.

To implement todo mode functionality, we need:

1. Define a todo mode protocol for the Agent to see
2. Provide the Agent with the ability to create and maintain todo lists
3. Prompt the current todo list status during Agent operation

### Todo Mode Protocol

Here we use a JSON list format:

```json
[
        {"task": "Task 1", "done": true},
        {"task": "Task 2", "done": false}
]
```

Or more rigorously, shown in JSON schema format:

```json
{
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task description"},
            "done": {"type": "boolean", "description": "Whether completed"}
        },
        "required": ["task", "done"]
    }
}
```

### InternalTools Provided to Agent

For creating, modifying, and maintaining todo lists, in past workflow designs, we could force our LLM application to generate a workflow initially and update the todo list after each tool execution based on tool execution results. However, with improving model capabilities, especially the popularity of agentic training, current models are fully capable of supporting another pattern: providing the Agent with a set of tools that can create and maintain todo lists.

However, these tools differ from the @Tool tools we previously provided. The previous tools operated on external files and APIs, but todo tools need to operate on the Agent's running state (todo list). To achieve this, we need: (1) abstract an AgentState containing properties like messages, todo list, current_mode, etc.; (2) design a new tool class (InternalTool) whose schema provided to LLM doesn't contain the state parameter, but can actually handle AgentState.

```python
class AgentState(BaseModel):
    """Agent State Class

    Stores conversation messages, current mode, permission overrides, temporary states, todo items, etc.
    """
    messages: list[dict] = []
    current_mode: Literal["plan", "default", "auto_edit"] = "default"
    override_authorization: dict[str, Permission] = {}
    tmp_states: dict = {}
    todo_list: list = []

    def clear_state(self):
        """Clear state, reset all fields"""
        self.messages = []
        self.tmp_states = {}
        self.todo_list = []
```

```python
@internal_tool(default_permission=Permission.ALLOW)
def create_todo(state, tasks: list[dict]) -> str:
    """Create new todo list, replace current list

    Todo list format example:
    [
        {"task": "Task 1", "done": true},
        {"task": "Task 2", "done": false}
    ]

    Args:
        tasks: Todo list, each item contains task(description) and done(whether completed)

    Returns:
        Operation result message
    """
    # 1. Use jsonschema.validate to validate tasks format
    validate_todo_list(tasks)

    # 2. Set state.todo_list = tasks
    state.todo_list = tasks

    # 3. Return success message
    task_count = len(tasks)
    return f"Successfully created todo list with {task_count} tasks"
```

### Prompting Todo List Status

We can insert a user_message into the messages list **before each LLM call**, containing the current todo list JSON.

## Persistence

We previously defined an AgentState, so naturally we can serialize this state class and store it in the file system to achieve persistence. In the CLI program, use `--resume xxx` to load previous run records and restore the previous state. But when should we persist? It seems many places could include persistence, such as before and after LLM calls, before and after tool execution... and so on. Combined with the previous todo list and earlier permission control, they all involve inserting an operation at some point in the ReAct Loop, so we can naturally extract a concept: Hook. Abstract the series of methods that need to be executed at a certain point into a hooks list, and execute corresponding tasks in sequence at that position.

```python
# 1. Execute pre_user_query_hooks
        for hook in self.pre_user_query_hooks:
            continue_execution, hook_msg = hook(self.state)
            if hook_msg is not None:
                yield hook_msg
            if not continue_execution:
                return
```

Finally, we can use hooks to define an add_todo_message(state) function and add it to pre_llm_call_hooks. Before each LLM call, insert a user_message into the messages list containing the current todo list JSON.

At this point, the complete code can be found in `agents/state_cli_agent.py`
