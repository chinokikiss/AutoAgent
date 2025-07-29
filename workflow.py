import re
import os
import ast
import time
import json
import random
import tempfile
from init import Config
from winotify import Notification
import threading

from rich.console import Console

class Flowchart:
    def __init__(self, mermaid_text):
        self.mermaid_text = mermaid_text
        self.nodes, self.connections = self.parse_mermaid_flowchart(mermaid_text)
        self.nodes['0'] = ''
        self.connections = [['0', 'A']] + self.connections
        self.t = {}
        self.results = {}
        self.traversal(['0', 'A'])
    
    def begin(self, node):
        lst1 = []
        lst2 = []
        for connection in self.connections:
            if connection[0] == node:
                if len(connection) == 2:
                    lst1.append(connection)
                elif len(connection) == 3:
                    lst2.append(connection)
        
        if lst2:
            result = ''
            for i in self.end(node):
                if i[0] in self.results:
                    result += '\n\n'+self.results[i[0]]
            
            choices = [i[1] for i in lst2]

            content = self.function_node(node, result, choices)
            for i in lst2:
                if f'[{i[1]}]' in content:
                    break
            lst2 = [i]
        
        return lst1+lst2

    def end(self, node):
        lst = []
        for connection in self.connections:
            if connection[-1] == node:
                lst.append(connection)
        return lst
    
    def back_traversal(self, connection, has_nodes=[]):
        if connection[0] not in has_nodes:
            has_nodes.append(connection[0])
            for i in self.end(connection[0]):
                self.back_traversal(i, has_nodes)
        return has_nodes
    
    def traversal(self, connection):
        current_thread = threading.current_thread()
        self.t[current_thread.ident] = connection[0]

        end_connections = self.end(connection[0])
        if len(end_connections) > 1:
            while True:
                back_nodes = self.back_traversal(connection)
                t = self.t.copy()
                del t[current_thread.ident]
                for i in t.values():
                    if i in back_nodes:
                        break
                else:
                    break
                time.sleep(0.1)
        
        if connection[0] in self.results and self.results[connection[0]]:
            print(self.mermaid_text)
            print('并行模块出现问题！')
        
        result = ''
        for i in end_connections:
            if i[0] in self.results:
                result += '\n\n'+self.results[i[0]]
        
        branch = []
        for i in self.connections:
            if i[0] == connection[0]:
                if len(i) == 3:
                    branch.append(i)

        if branch:
            self.results[connection[0]] = result
        else:
            self.results[connection[0]] = self.function_node(connection[0], result)


        if connection[-1] in self.t.values():
            del self.t[current_thread.ident]
        else:
            begin_connections = self.begin(connection[-1])
            for connection in begin_connections[1:]:
                threading.Thread(target=self.traversal, args=(connection,)).start()
            if begin_connections:
                self.traversal(begin_connections[0])
            else:
                del self.t[current_thread.ident]
                if len(self.t) == 0:
                    if Config.wait:
                        console = Console()
                        console.file.write("\033[1A\033[2K")
                        console.print(f"\n[green]▶[/green] 工作流 [bold]{self.nodes['A']}[/bold] [bright_green]✓ 完成[/bright_green]")
                        console.print("[bold yellow]\nUser: [/bold yellow]", end='')
                    Config.messages.put([self.nodes['A'], self.results])
                    toast = Notification(
                        app_id="AutoAgent",
                        title="AutoAgent", 
                        msg=f"工作流 {self.nodes['A']} 已完成",
                        duration="long"
                    )
                    toast.show()
    
    def function_node(self, node, result, choices=[]):
        node_result = ''
        node_content = self.nodes[node]
        match = re.match(r"([a-zA-Z_]\w*)\s*(\{.*\})", node_content)
        if match:
            function_name = match.group(1)
            args = match.group(2)
            args = ast.literal_eval(args)

            result = f'以下是上个节点传递过来的结果:\n' + result
            result = f'你是工作流中的 {node} 节点\n' + result
            result = f'工作流中各节点返回结果情况: {self.results}\n' + result
            result = f'一个工作流: \n{self.mermaid_text}\n\n' + result

            agent_id = random.randint(1, 1000)
            temp_data = {
                "task_content": f'"""\n{result}\n"""\n请根据以上结果，完成以下任务: '+args["task_content"] if result else args["task_content"],
                "agent_id": agent_id
            }
            if function_name == "CLI_Agent":
                py = 'CLIAgent.py'
                temp_data["WORKDIR"] = Config.WORKDIR
            elif function_name == "GUI_Agent":
                py = 'GUIAgent.py'
            elif function_name == "Web_Agent":
                py = 'WebAgent.py'
            elif function_name == "Text_Agent":
                pass
            else:
                raise "错误的函数名"

            if len(choices) > 0:
                args["task_content"] += f"最后工作报告中从选项:'{choices}'中选择一个，输出格式为: [选项]"

            if function_name == "Text_Agent":
                response = Config.client.chat.completions.create(
                    model='Qwen/Qwen3-235B-A22B-Instruct-2507',
                    messages=[{'role':'user', 'content':f'输入文本是:\n"""\n{result}\n"""\n请根据输入文本完成以下任务:"{args["task_content"]}"'}]
                )

                node_result = response.choices[0].message.content
            else:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                    json.dump(temp_data, f, ensure_ascii=False)
                    temp_file = f.name

                os.system(f'start /min cmd /c python {py} "{temp_file}"')
            
                while True:
                    if agent_id in Config.Agent_return:
                        node_result = Config.Agent_return[agent_id]
                        del Config.Agent_return[agent_id]
                        break
                    time.sleep(0.1)

        return node_result
    
    def parse_mermaid_flowchart(self, text):
        nodes = {}
        connections = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('flowchart') or not line:
                continue
            
            square_nodes = re.findall(r'([A-Z]+)\[([^]]+)]', line)
            for node_id, node_label in square_nodes:
                nodes[node_id] = node_label
            
            curly_nodes = re.findall(r'([A-Z]+)\{(.+)\}', line)
            for node_id, node_label in curly_nodes:
                nodes[node_id] = node_label
            
            if '-->' in line:
                labeled_match = re.search(r'([A-Z]+)\s*-->\|([^|]+)\|\s*([A-Z]+)', line)
                if labeled_match:
                    from_node = labeled_match.group(1)
                    label = labeled_match.group(2)
                    to_node = labeled_match.group(3)
                    connections.append([from_node, label, to_node])
                else:
                    parts = line.split('-->')
                    if len(parts) == 2:
                        left_side = parts[0].strip()
                        right_side = parts[1].strip()

                        source_ids = re.findall(r'([A-Z]+)(?:\[[^\]]*\]|\{[^}]*\})?', left_side)      
                        dest_id_match = re.match(r'([A-Z]+)', right_side)
                        
                        if dest_id_match:
                            dest_node = dest_id_match.group(1)                    
                            for src_node in source_ids:
                                connections.append([src_node, dest_node])
        
        return nodes, connections