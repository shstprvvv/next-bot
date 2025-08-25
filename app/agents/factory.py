from langchain.agents import AgentExecutor, create_react_agent
from langchain.memory import ConversationBufferMemory

from app.agents.prompts import get_agent_prompt, get_wb_agent_prompt


def create_agent_executor(llm, tools, is_background_agent: bool = False) -> AgentExecutor:
    prompt = get_wb_agent_prompt() if is_background_agent else get_agent_prompt()
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=True,
        handle_parsing_errors=True,
    )


