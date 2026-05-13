from typing import TypedDict
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI

SYSTEM_PROMPT = "You are helpful."
llm = ChatOpenAI(model="gpt-4o-mini")

class State(TypedDict, total=False):
    messages: list
    draft: str
    route: str

def router(state: State):
    msg = state["messages"][-1]
    res = llm.invoke([SYSTEM_PROMPT, msg])
    return {"route": "writer", "messages": [res]}

def writer(state: State):
    msg = state.get("messages")
    res = llm.invoke(msg)
    return {"draft": str(res)}

workflow = StateGraph(State)
workflow.add_node("router", router)
workflow.add_node("writer", writer)
workflow.set_entry_point("router")
workflow.add_edge("router", "writer")
workflow.set_finish_point("writer")
graph = workflow.compile()
