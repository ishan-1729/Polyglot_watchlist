"""Local, human-reviewed orchestration; importing this package loads no model."""

import os

# The pilot never sends traces or fetches models, regardless of shell defaults.
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGGRAPH_STRICT_MSGPACK'] = 'true'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
