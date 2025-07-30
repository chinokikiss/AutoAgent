import os
import toml
from openai import OpenAI

with open('config.toml', 'r', encoding='utf-8-sig') as f:
    config_text = f.read()
config = toml.loads(config_text)

if not config['api_key']:
    raise Exception("请填写 config.toml 的 api_key 字段")
os.makedirs('work', exist_ok=True)

class Config:
    WORKDIR = os.path.dirname(__file__)+'\work'

    client = OpenAI(
        api_key=config['api_key'],
        base_url=config['base_url']
    )

for key, value in config.items():
    setattr(Config, key, value)