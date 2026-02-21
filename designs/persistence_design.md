# 状态持久化设计

**应用于state_cli_agent.py**

1. 为Agent类增加一个tmpdir参数，用于指定持久化的文件放在哪个目录下

2. AgentState增加一个name属性，在启动时或者/clear时，根据name生成一个唯一的文件名

3. 增加一个persist的hook函数，用于将当前的state持久化到{tmpdir}/{name}.json中；将这个hook添加每一个hooks列表里
    3.1 在state_cli_agent中将没有实际插入流程的hooks的调用逻辑补充进去

4. Agent类的初始化方法增加一个load_persist: str = None参数，用于指定是否/从哪个文件加载持久化的状态

5. CLI类增加一个--resume参数：
    * 如果只输入--resume， 那么就打印所有的tmpdir下的文件
    * 如果输入--resume {name}或--resume {name}.json， 那么就从{tmpdir}/{name}.json加载状态