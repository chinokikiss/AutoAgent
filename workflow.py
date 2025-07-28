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

class Flowchart:
    def __init__(self, mermaid_text):
        self.nodes, self.connections = self.parse_mermaid_flowchart(mermaid_text)
        self.nodes['0'] = ''
        self.connections = [['0', 'A']] + self.connections
        self.t = {}
        self.results = {}
        self.traversal(['0', 'A'])
    
    def begin(self, node, result):
        lst1 = []
        lst2 = []
        for connection in self.connections:
            if connection[0] == node:
                if len(connection) == 2:
                    lst1.append(connection)
                elif len(connection) == 3:
                    lst2.append(connection)
        
        if lst2:
            choices = [i[1] for i in lst2]
            response = Config.client.chat.completions.create(
                model='Qwen/Qwen3-235B-A22B-Instruct-2507',
                messages=[{'role':'user', 'content':f'输入文本是:\n"""\n{result}\n"""\n请根据输入文本和问题:"{self.nodes[node]}"，从选项:"{choices}"中选择一个，输出格式为: [选项]'}]
            )
            content = response.choices[0].message.content
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
    
    def back_traversal(self, connection, ident, has_nodes=[]):
        if connection[0] not in has_nodes:
            has_nodes.append(connection[0])
            for i in self.end(connection[0]):
                t = self.t.copy()
                del t[ident]
                if i[0] in t.values():
                    return True
                if self.back_traversal(i, ident, has_nodes):
                    return True
        return False
    
    def traversal(self, connection):
        current_thread = threading.current_thread()
        self.t[current_thread.ident] = connection[0]

        end_connections = self.end(connection[0])
        if len(end_connections) > 1:
            while True:
                if not self.back_traversal(connection, current_thread.ident):
                    break
                time.sleep(0.1)
        
        result = ''
        for i in end_connections:
            if i[0] in self.results:
                result += '\n\n'+self.results[i[0]]
        
        node_content = self.nodes[connection[0]]
        match = re.match(r"([a-zA-Z_]\w*)\s*(\{.*\})", node_content)
        if match:
            function_name = match.group(1)
            args = match.group(2)
            args = ast.literal_eval(args)

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
            else:
                raise "错误的函数名"

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(temp_data, f, ensure_ascii=False)
                temp_file = f.name

            os.system(f'start /min cmd /c python {py} "{temp_file}"')
        
            while True:
                if agent_id in Config.Agent_return:
                    self.results[connection[0]] = Config.Agent_return[agent_id]
                    result = Config.Agent_return[agent_id]
                    del Config.Agent_return[agent_id]
                    break
                time.sleep(0.1)
        
        elif '?' in node_content:
            self.results[connection[0]] = result

        elif node_content and connection[0] != 'A' and node_content not in ['结束']:
            response = Config.client.chat.completions.create(
                model='Qwen/Qwen3-235B-A22B-Instruct-2507',
                messages=[{'role':'user', 'content':f'输入文本是:\n"""\n{result}\n"""\n请根据输入文本完成以下任务:"{node_content}"'}]
            )
            self.results[connection[0]] = response.choices[0].message.content

        if connection[-1] in self.t.values():
            del self.t[current_thread.ident]
        else:
            begin_connections = self.begin(connection[-1], result)
            for connection in begin_connections[1:]:
                threading.Thread(target=self.traversal, args=(connection,)).start()
            if begin_connections:
                self.traversal(begin_connections[0])
            else:
                del self.t[current_thread.ident]
                if len(self.t) == 0:
                    Config.messages.put(self.results)
                    toast = Notification(
                        app_id="AutoAgent",
                        title="AutoAgent", 
                        msg=f"工作流 {self.nodes['A']} 已完成",
                        duration="long"
                    )
                    toast.show()
    
    def parse_mermaid_flowchart(self, text):
        nodes = {}
        connections = []
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('flowchart') or not line:
                continue
            
            square_nodes = re.findall(r'([A-Z]+)\[([^\]]+)\]', line)
            for node_id, node_label in square_nodes:
                nodes[node_id] = node_label
            
            curly_nodes = re.findall(r'([A-Z]+)\{([^}]+)\}', line)
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
                    all_nodes_in_line = re.findall(r'([A-Z]+)(?:\[[^\]]+\]|\{[^}]+\})?', line)
                    if len(all_nodes_in_line) >= 2:
                        connections.append([all_nodes_in_line[0], all_nodes_in_line[1]])
        
        return nodes, connections