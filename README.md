# awesome_agent_loop

这个项目旨在逐步由易到难，通过逐步实践学习LLM agent的核心-Agent Loop的各种形态。

本项目没有任何新东西，目标也不是建立一个production-ready的工具，纯粹是帮助个人启发式地进行学习。

## 基础

我们将使用litellm来处理llm调用，同时用vibe的方式去实现tools，把学习的重点放在agent loop上

## 这个项目有什么

* 从最简单的ReAct循环到类openclaw的主动、持久的Agent，甚至于多agent
* 能够调用工具的Agent
* 最简但可用的CLI界面

## 这个项目不会有什么

* 多模态输入输出
* 复杂的异步编程，如MCP
* 一些繁琐但**重要**的功能，如权限管理。所以请不要把这个项目用到**任何严肃的场景**
* 对用户友好的界面，如web ui以及更养眼的cli界面
* 与一些复杂的协议进行交互，如MCP，A2A，乃至claw类应用的各种gateway。你完全可以去nanobot寻找更完善的实现

## 这个项目含AI量多少？是vibe coding的产物么？

我个人其实不介意这个问题，因为我在工作中已经有98%(如果不是99%)的代码是通过AI写的了。

但是这个项目除外，因为我追求的不是成品（你可以找到一大堆agent loop，nanobot,deepAgents等），这个项目的宗旨是Learn By Doing，通过实践来掌握agent的底层设计（相当简单！）

总的来说，tools基本是使用claude code和open code生成的，各种agent loop的形态尽管少不了trae提供的AI补全，但是大部分代码行可以认为是人工编写的

我会用AI生成一些中间性质的文档，但最终我会把这一过程中的实现细节以及思考用自己的语言写成一篇（或多篇）文章。

## 计划
[x] 1. 一个简单ReAct循环
    [x] tool call
    [x] 单轮对话的Agent Loop
[ ] 2. 一个CLI多轮对话Agent工具
    [x] CLI与多轮对话
    [x] 处理中断
    [ ] session与continue
    [ ] 上下文压缩
[ ] 3. 一个claw式的主动、持久的Agent
    [ ] 分层记忆
    [ ] 定时任务
    [ ] skill，以及自进化（自行安装寻找skill）
[ ] 4. multiAgent
    [ ] 串行subAgent(sub agent as a tool)
    [ ] Agent Teams（后台并行执行，相互通信）

## 实现细节

详细的代码实现说明请参见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)。

## 参考资料

* [https://agentic-patterns.com](https://agentic-patterns.com)
* [nanobot](https://github.com/HKUDS/nanobot)
