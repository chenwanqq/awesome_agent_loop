# awesome_agent_loop

这个项目旨在逐步由易到难，通过逐步实践学习LLM agent的核心-Agent Loop的各种形态。

本项目没有任何新东西，目标也不是建立一个production-ready的工具，纯粹是帮助个人启发式地进行学习。

## 基础

我们将使用litellm来处理llm调用，同时用vibe的方式去实现tools，把学习的重点放在agent loop上

## 计划
[ ] 1. 简单ReAct循环
    [x] 1.0 tool call
    [x] 1.1 单轮对话的Agent Loop
[ ] 2. 一个CLI多轮对话Agent工具
    [ ] 1.2 CLI与多轮对话
    [ ] 1.3 处理打断
    [ ] 1.4 Skill以及更复杂的system prompt的组合
    [ ] 1.5 流式输出
    [ ] 1.6 session
    [ ] 1.7 权限与
    [ ] 1.8 mcp
    [ ] 1.9 hook
[ ] 3. 记忆功能
    [ ] 3.1 结构化上下文
    [ ] 3.2 类claw式的分层记忆
    [ ] 3.3 上下文压缩
[ ] 4. multiAgent
    [ ] 4.1 串行subAgent(sub agent as a tool)
    [ ] 4.2 Agent Teams（后台并行执行，相互通信）

## 实现细节

详细的代码实现说明请参见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)。

## 参考资料

* [https://agentic-patterns.com](https://agentic-patterns.com)
* [nanobot](https://github.com/HKUDS/nanobot)
