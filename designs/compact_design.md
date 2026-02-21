# 上下文压缩设计

**应用于middleware_cli_agent.py**

## 触发时机
1. 手动执行/compact指令
2. 当上下文长度达到压缩阈值时

## 压缩方式

0. 保留最开头role为system的message和最近的n条消息的完整记录，其余的执行以下操作：
1. reasoning_content如果存在则删除
2. tool_call和content里，如果长度超过阈值max_content_length,则将原始内容存放到session_dir({tmp_dir}/{name})下的一个文件(xxx.json,用uuid生成文件名)里，将内容变为"xxxxx(长度为max_content_length)...更多请参见{tmp_dir}/{name}/xxx.json"
3. 使用litellm的token_counter来计算压缩后的token长度，如果仍超过阈值max_compacted_length，则执行一下操作
4. 使用llm进行压缩，消息为
```json
[
    {"role": "system", "content": "你的任务是对历史消息进行压缩，以节省上下文空间。请你输出一段不超过2000字的summary，简单概括之前agent与user进行了什么交互。用户给agent赋予的角色是:{system_prompt}，用户前{n}次的输入为{若干条user message},待压缩的信息为{除了system message和最近n条消息以外的所有消息}"},
]
```
5. 用第4步得到的结果来替换当前的message中被压缩的信息，即
```json
[
    {"role": "system",content:"xxx"},//保留原system_message不变
    {"role": "assistant",content: "摘要信息"},
    ... //保留最近的n条消息的完整记录
]
```



## 实现细节

1. 在AgentState中增加一个total_tokens参数
2. 使用Middleware机制实现上下文压缩功能
    * 增加一个hook用于压缩上下文，在pre_llm_call_hook中调用；
    * 增加一个更新total_tokens的hook，在post_llm_call_hook中调用；
3. 使用middleware，新增一个/compact 指令，用于手动触发上下文压缩