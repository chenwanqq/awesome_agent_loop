## todo list的设计


1. todo list 放在AgentState中，是一个json列表，形如
```json
[
    {
        "task": "task1",
        "done": true
    },
    {
        "task": "task2",
        "done": false
    },
]
```
需要用json schema来进行校验，保证规则定义

2. 定义一个新的InternalTool的基类，与之前的Tool的最大区别在于InternalTool可以访问AgentState(tool call的argument中不包含state的参数，但是将tool call的参数和state一起传入InternalTool的实际运行逻辑)。InternalTool使用包装器模式，@InternalTool装饰器放在实际运行逻辑的上面，并和现有的Tool一样支持导出schema

3. 因此需定义若干InternalTool，包括
    1. create_todo: 创建新的todo列表
    2. edit_todo: 编辑todo列表,接收old_todo和new_todo两个参数，old_todo与AgentState中实际存储的比较一致后，更新为new_todo
    3. clear_todo: 清空todo

4. todo list存在于消息中的方式：如果存在todo list,那么使用在每次llm调用前，将原有的`<todo></todo>`包裹的message删除，插入一条user message，使用`<todo></todo>`包裹todo list；

5. AgentLoop的修改仅限于state_cli_agent.py;新加入的InternalTool和todo list的逻辑放在一个新的InternalTools文件夹下；