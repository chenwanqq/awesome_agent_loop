# awesome_agent_loop

这个项目旨在逐步由易到难，通过逐步实践学习LLM agent的核心-Agent Loop的各种形态。

本项目没有任何新东西，目标也不是建立一个production-ready的工具，纯粹是帮助个人启发式地进行学习。

## 基础

我们将使用litellm来处理llm调用

## 计划

[ ] 1. 简单ReAct循环
    [ ] 1.0 tool call
    [ ] 1.1 AgentLoop的实现
    [ ] 1.2 System prompt
    [ ] 1.2 CLI与处理打断
    [ ] 1.3 Skill
[ ] 2. 记忆功能
    [ ] 2.1 结构化上下文
    [ ] 2.2 类claw式的分层记忆
    [ ] 2.3 Rag
[ ] 3. 如何处理打断
[ ] 4. multiAgent
    [ ] 4.1 串行subAgent(sub agent as a tool)
    [ ] 4.2 Agent Teams（后台并行执行，相互通信）
## 参考资料
[https://agentic-patterns.com](https://agentic-patterns.com)
