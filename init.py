import os
import toml
from openai import OpenAI

with open('config.toml', 'r', encoding='utf-8-sig') as f:
    config_text = f.read()
config = toml.loads(config_text)

class Config:
    WORKDIR = os.path.dirname(__file__)

    client = OpenAI(
        api_key=config['api_key'],
        base_url=config['base_url']
    )

for key, value in config.items():
    setattr(Config, key, value)