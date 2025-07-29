import os
import re
import api
import json
import time
import pyfiglet
import threading
from PIL import Image
from queue import Queue
from init import Config
from datetime import datetime
from workflow import Flowchart

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.padding import Padding
from rich.syntax import Syntax
from rich.align import Align

console = Console()

threading.Thread(target=api.main).start()

print(pyfiglet.figlet_format("AutoAgent", font="big"))

with open('agents.json', 'r', encoding='utf-8') as f:
    agents = json.load(f)

SYSTEM_PROMPT = """
今天是%s

你是AutoAgent，一个专业的多智能体工作流编排助手。你可以通过设计和执行工作流来调用其他专业智能体，协同完成复杂任务。

重要约束：
- 你只能使用提供的tools工具（workflow_demo和workflow_executor）
- 你不能直接调用任何agent
- 所有agent的调用必须通过workflow_executor工具执行工作流来实现
- 你无法直接与其他智能体交互，只能通过工作流编排的方式间接调用
- 下载图片、视频等网络资源尽量使用Web_Agent，不要用CLI_Agent

你的核心能力：
1. 分析用户需求，设计合理的工作流程
2. 使用Mermaid flowchart语法编写工作流代码
3. 支持串行、并行和条件判断的复杂流程控制
4. 先展示工作流程图供用户确认，确认后执行工作流

你可以使用的智能体：
%s

工作流编写规范：
- 使用 flowchart TD 格式
- 节点名必须是单个字母
- 头节点必须是 A[工作流取名]
- 结束节点格式：必须是 节点名[结束]
- 其他节点(包括分支节点、功能节点)必须使用agent调用格式：agent_name{"task_content":"任务内容和agent应该返回什么结果"}

工作流设计原则：
- 正常情况下工作流尽量设计的简短一些，类似的步骤可以合并在一起，提倡高效
- 相同Agent的连续或相似任务应该合并成一个调用，在task_content中包含多个子任务
- 适当设计试错机制：对于可能失败的关键步骤，添加条件判断节点检查执行结果
- 失败时应返回到上一个节点或提供备选方案，避免整个流程中断
- 对于网络请求、文件操作等易出错的操作，预设重试或降级方案
- 如果不清楚用户所说的一些专有名词的含义，那么可以加个步骤在前面，先搜索这些专有名词的含义

工作流示例：
```mermaid
flowchart TD
A[混合信息收集] --> B[Web_Agent{"task_content":"搜索相关资料和最新信息"}]
A --> C[CLI_Agent{"task_content":"检查本地文件和资源"}]
B --> D{Text_Agent{"task_content":"搜索结果满足需求?"}}
D -->|是| E[Text_Agent{"task_content":"合并搜索结果"}]
D -->|否| F[Web_Agent{"task_content":"使用不同关键词重新搜索"}]
C --> G[CLI_Agent{"task_content":"执行系统命令和环境检查"}]
E --> H[Text_Agent{"task_content":"处理和整理信息"}]
F --> H
G --> H
H --> I[结束]
```

工作流程：
1. 分析用户任务需求
2. 设计工作流程并用workflow_demo工具展示
3. 等待用户确认
4. 用户确认后，使用workflow_executor工具执行
""" % (agents, f"{datetime.today().strftime('%Y年%m月%d日')}，{datetime.today().strftime('%A')}")

tools = [
    {
        "type": "function",
        "function": {
            "name": "workflow_demo",
            "description": "工作流演示工具，用于展示Mermaid格式的工作流程图给用户预览和确认。接收Mermaid flowchart代码，生成可视化的流程图展示，让用户了解任务执行的完整流程和各个步骤的关系。支持串行、并行、条件判断等复杂流程的可视化展示。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mermaid_code": {
                        "type": "string",
                        "description": "Mermaid flowchart格式的工作流代码，必须以flowchart TD开头，包含完整的节点定义和连接关系"
                    }
                },
                "required": ["mermaid_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "workflow_executor",
            "description": "工作流执行器，根据Mermaid工作流代码按顺序执行各个Agent任务。支持串行执行、并行处理和条件判断。会解析工作流中的function节点，提取task_content参数，然后调用相应的Agent执行任务。具备流程控制、错误处理、结果汇总等功能，确保复杂工作流的可靠执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mermaid_code": {
                        "type": "string",
                        "description": "已确认的Mermaid flowchart格式工作流代码"
                    }
                },
                "required": ["mermaid_code"]
            }
        }
    }
]

first_message = """我是AutoAgent，一个专业的多智能体工作流编排助手。我的核心职责是通过设计和执行工作流来协调多个专业AI智能体（CLI_Agent、GUI_Agent、Web_Agent、Text_Agent），帮助用户完成复杂任务。

**我的工作方式：**
  **分析需求**：理解您的任务目标，拆解为可执行的步骤
  **设计工作流**：用Mermaid语法编排智能体协作流程
  **可视化确认**：生成流程图供您预览
  **执行监控**：按确认后的工作流调用对应智能体

需要执行具体任务时，请告诉我需求，我将为您生成完整的工作流方案！"""

def append_tool_msg(message):
    global messages

    tool_call_id = f"call_{int(time.time()*1000)}"
    messages.append({
        'role': 'assistant', 
        'content': '', 
        'tool_calls': [
            {
                'id': tool_call_id,
                'type': 'function',
                'function': {
                    'name': 'workflow_executor',
                    'arguments': ''
                }
            }
        ]
    })
    messages.append({
        'role': 'tool',
        'content': f"执行完毕: workflow - {message}",
        'tool_call_id': tool_call_id
    })

workflow_demo = None
Config.messages = Queue()
Config.Agent_return = {}
Config.wait = True
messages = [{"role": "system", "content": SYSTEM_PROMPT}]
console.print(Panel(Text(first_message, style="bold blue"), title="AutoAgent", border_style="blue"))
while True:
    while not Config.messages.empty():
        name, message = Config.messages.get()
        append_tool_msg(message)
        console.print(f"\n[green]▶[/green] 工作流 [bold]{name}[/bold] [bright_green]✓ 完成[/bright_green]\n")
    
    Config.wait = True
    user_content = console.input("[bold yellow]\nUser: [/bold yellow]")
    Config.wait = False
    
    while not Config.messages.empty():
        name, message = Config.messages.get()
        append_tool_msg(message)

    if user_content.lower() == 'exit':
        os._exit(0)

    elif user_content.lower()[:2] == 'cd':
        dir_name = user_content[3:]
        if os.path.isdir(dir_name):
            Config.WORKDIR = dir_name
            console.print(Panel(Align.center(Text(f"已切换到目录: '{dir_name}'", style="bold green")), title="Success", title_align="left", border_style="green", padding=(0, 1)))
        else:
            console.print(Panel(Align.center(Text(f"目录 '{dir_name}' 不存在", style="bold red")), title="Failure", title_align="left", border_style="red", padding=(0, 1)))
    
    elif user_content.lower()[:5] == 'clear':
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        console.print(Panel(Align.center(Text(f"已清空上下文，可以无视之前的对话", style="bold green")), title="Success", title_align="left", border_style="green", padding=(0, 1)))
    
    elif user_content.lower()[:3] == 'run':
        if workflow_demo:
            tool_call_id = f"call_{int(time.time()*1000)}"
            messages.append({'role': 'user', 'content': 'run'})
            messages.append({
                'role': 'assistant', 
                'content': '', 
                'tool_calls': [
                    {
                        'id': tool_call_id,
                        'type': 'function',
                        'function': {
                            'name': 'workflow_executor',
                            'arguments': workflow_demo
                        }
                    }
                ]
            })
            threading.Thread(target=Flowchart, args=(workflow_demo,)).start()
            messages.append({
                'role': 'tool',
                'content': f"执行成功: workflow_executor - 正在工作中...",
                'tool_call_id': tool_call_id
            })
            console.print(Panel(Align.center(Text(f"已成功运行工作流 '{workflow_name}'，正在工作中...", style="bold green")), title="Success", title_align="left", border_style="green", padding=(0, 1)))
        else:
            console.print(Panel(Align.center(Text(f"请先让AutoAgent生成示例工作流", style="bold red")), title="Failure", title_align="left", border_style="red", padding=(0, 1)))

    else:
        messages.append({"role": "user", "content": user_content})

        response = Config.client.chat.completions.create(
            model = 'Qwen/Qwen3-235B-A22B-Thinking-2507',
            messages=messages,
            stream=True,
            tools=tools
        )

        with console.status("[bold blue]🤔 thinking...[/bold blue]", spinner="dots"):
            assistant_message = {'role': 'assistant', 'content': ''}
            response_content = ""
            reasoning = True
            
            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    if delta.reasoning_content:
                        continue
                    
                    if delta.content:
                        response_content += delta.content
                        assistant_message['content'] += delta.content
                    
                    if delta.tool_calls:
                        if 'tool_calls' not in assistant_message:
                            assistant_message['tool_calls'] = []
                        for tool_call in delta.tool_calls:
                            while len(assistant_message['tool_calls']) <= tool_call.index:
                                assistant_message['tool_calls'].append({})
                            
                            if tool_call.id:
                                assistant_message['tool_calls'][tool_call.index]['id'] = tool_call.id
                            if tool_call.type:
                                assistant_message['tool_calls'][tool_call.index]['type'] = tool_call.type
                            if 'function' not in assistant_message['tool_calls'][tool_call.index]:
                                assistant_message['tool_calls'][tool_call.index]['function'] = {'name': '', 'arguments': ''}
                            if tool_call.function.name:
                                assistant_message['tool_calls'][tool_call.index]['function']['name'] = tool_call.function.name
                            if tool_call.function.arguments is not None:
                                assistant_message['tool_calls'][tool_call.index]['function']['arguments'] += tool_call.function.arguments or ''

        console.print("\n[bold green]AutoAgent:[/bold green]")
        if response_content:
            console.print(Panel(Text(response_content, style="cyan"), title="Response", border_style="blue"))
    
        messages.append(assistant_message)

        if assistant_message.get('tool_calls'):
            for tool_call in assistant_message['tool_calls']:
                try:
                    function_name = tool_call['function']['name']
                    arguments_str = tool_call['function']['arguments']
            
                    try:
                        pretty_args = json.dumps(json.loads(arguments_str), indent=2, ensure_ascii=False)
                        syntax = Syntax(
                            pretty_args, 
                            "json", 
                            theme="monokai", 
                            line_numbers=False, 
                            word_wrap=True,
                            tab_size=2
                        )
                    except json.JSONDecodeError:
                        syntax = Text(arguments_str, style="italic yellow")
                        syntax.overflow = "fold"

                    terminal_width = console.size.width
                    panel_width = min(120, terminal_width - 4)

                    console.print(
                        Panel(
                            Columns([
                                Text.from_markup(f"Function: [bold green]{function_name}[/bold green]"),
                                Padding(syntax, (0, 0, 0, 4))
                            ]),
                            title=f"Tool Call ID: {tool_call.get('id', 'N/A')}",
                            border_style="yellow",
                            width=panel_width,
                            expand=False
                        )
                    )
                    
                    if tool_call['function']['arguments']:
                        args = json.loads(tool_call['function']['arguments'])
                    else:
                        args = {}
                    
                    if function_name == "workflow_executor":
                        workflow_demo = args['mermaid_code']
                        try:
                            workflow_name = re.findall(r'A\[([^\]]+)\]', args['mermaid_code'])[0]
                        except:
                            workflow_name = ''
                            
                        threading.Thread(target=Flowchart, args=(args['mermaid_code'],)).start()
                        messages.append({
                            'role': 'tool',
                            'content': f"执行成功: {function_name} - 正在工作中...",
                            'tool_call_id': tool_call['id']
                        })
                        
                        console.print(Panel(Align.center(Text(f"已成功运行工作流 '{workflow_name}'，正在工作中...", style="bold green")), title="Success", title_align="left", border_style="green", padding=(0, 1)))
                    elif function_name == "workflow_demo":
                        workflow_demo = args['mermaid_code']
                        try:
                            workflow_name = re.findall(r'A\[([^\]]+)\]', args['mermaid_code'])[0]
                        except:
                            workflow_name = ''

                        def process_mermaid(txt):
                            txt = txt.strip('`').lstrip('mermaid').strip()
                            pattern = re.compile(r'([A-Z])([\[\{])([^\]}\n]*?){"task_content":"([^"]+)"}[\]}]')
                            def repl(m):
                                nid, bracket, agent, task = m.groups()
                                return f'{nid}{bracket}{nid} {agent} {task}{"]" if bracket == "[" else "}"}'
                            txt = pattern.sub(repl, txt)
                            txt = re.sub(r'\[([^[\]]*)\(([^)]*)\)([^[\]]*)\]', r'[\1\2\3]', txt)
                            txt = re.sub(r'["\'“”‘’:：]', '', txt)

                            return txt
                        
                        demo_code = process_mermaid(args['mermaid_code'])
                        with open("mermaid.mmd", "w", encoding="utf-8") as f:
                            f.write(demo_code)
                        os.system("mmdc -i mermaid.mmd -o mermaid.png -s 1")
                        img = Image.open('mermaid.png')
                        img.show()

                        messages.append({
                            'role': 'tool',
                            'content': f"执行成功: {function_name} - 结果保存在mermaid.png",
                            'tool_call_id': tool_call['id']
                        })
                    else:
                        raise "错误的函数名"
                    
                except Exception as e:
                    error_message = f"执行失败: {str(e)}"
                    console.print(Panel(Align.center(Text(f"执行工具: {function_name} - 失败: {str(e)}", style="bold red")), title="Failure", title_align="left", border_style="red", padding=(0, 1)))

                    messages.append({
                        'role': 'tool',
                        'content': error_message,
                        'tool_call_id': tool_call['id']
                    })