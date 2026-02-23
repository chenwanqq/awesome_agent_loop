# awesome_agent_loop

This project aims to progressively explore various forms of the Agent Loop—the core of LLM agents—from easy to difficult through hands-on practice.

There is nothing new in this project, and the goal is not to build a production-ready tool. It is purely for personal heuristic learning.

## Documentation

Detailed tutorial documents for this project:

| Document | Content | Code |
|----------|---------|------|
| [Preface](./doc/01-preview_en.md) | Project background and motivation | - |
| [Simple ReAct Agent](./doc/02-simple-react_en.md) | Basic ReAct loop, tool calling, context engineering | `agents/simple_react.py` |
| [Multi-turn Conversation and Plan Mode](./doc/03-multi-turns-plan_en.md) | CLI multi-turn conversation, permission control, plan mode implementation | `agents/simple_cli_react.py`, `agents/rich_cli_agent.py` |
| [Todo List and Persistence](./doc/04-todo-persistence-hook_en.md) | Todo list functionality, state persistence, hook design pattern | `agents/state_cli_agent.py` |
| [Middleware Architecture and Context Compaction](./doc/05-middleware-compaction_en.md) | Middleware architecture, context compaction and sliding window | `agents/middleware_cli_agent.py`, `middlewares/compact.py` |

## Basics

We will use litellm to handle LLM calls and implement tools in a "vibe" way, focusing our learning on the agent loop.

## What This Project Has

* From the simplest ReAct loop to OpenClaude-like proactive, persistent agents, and even multi-agent systems
* Agents that can call tools
* Minimal but usable CLI interface

## What This Project Will NOT Have

* Multimodal input/output
* Any guarantee of compatibility with multiple providers (I only have Kimi which is compatible with OpenAI format; I have not tested other LLM providers)
* Complex asynchronous programming such as MCP and streaming output
* User-friendly interfaces such as web UI or more polished CLI interfaces
* Interaction with complex protocols such as MCP, A2A, and various gateways for Claude-like applications. You can find more complete implementations in nanobot

## How Much AI Is Used in This Project? Is It Vibe Coding?

I personally don't mind this question because I already have 98% (if not 99%) of my code at work written by AI.

But this project is an exception because I'm not pursuing a finished product (you can find plenty of agent loops: nanobot, deepAgents, etc.). The purpose of this project is "Learn By Doing"—mastering the underlying design of agents through practice (which is quite simple!).

Generally speaking, the tools are mostly generated using Claude Code and Open Code. While various agent loop forms benefit from AI completion provided by Trae, most lines of code can be considered manually written.

All commit messages are AI-generated.

I use AI to generate some intermediate documents, but ultimately I write the implementation details and thoughts in my own language into one (or more) articles.

## Roadmap

- [x] 1. A Simple ReAct Loop

    - [x] Tool call
    - [x] Single-turn conversation Agent Loop (`agents/simple_react.py`)

- [x] 2. A CLI Multi-turn Conversation Agent Tool

    - [x] CLI and multi-turn conversation
    - [x] Handling interrupts (`agents/simple_cli_react.py`)
    - [x] Permissions (middleware)
    - [x] Plan mode (`agents/rich_cli_agent.py`)
    - [x] Todo list
    - [x] Persistence: session and continue (`agents/state_cli_agent.py`)
    - [x] Context compaction and sliding window (`agents/middleware_cli_agent.py`)

- [ ] 2. MultiAgent

    - [ ] Sequential subAgent (sub agent as a tool)
    - [ ] Task (replaces todo)
    - [ ] Agent Teams (background parallel execution, mutual communication)

- [ ] 3. A Claude-like Proactive, Persistent Agent

    - [ ] Hierarchical memory
    - [ ] Scheduled tasks
    - [ ] Skills, and self-evolution (self-installing and finding skills)

## References

* [Various Agent Patterns](https://agentic-patterns.com)
* [Direct code reference - nanobot](https://github.com/HKUDS/nanobot)
* [More comprehensive tutorial - Building Agents from Scratch](https://github.com/datawhalechina/hello-agents)
