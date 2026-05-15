from typing import TypedDict
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI
from agentir_langgraph.decorators import llm_call, writes
from agentir_langgraph.graph_proxy import GraphProxy


SYSTEM_PROMPT = "You are helpful."
llm = ChatOpenAI(model="gpt-4o-mini")

class State(TypedDict, total=False):
    messages: list
    draft: str
    route: str

@writes("route", "messages")
@llm_call(model="gpt-4o-mini", reads=["messages"], static_vars=["SYSTEM_PROMPT"])
def router(state: State):
    msg = state["messages"][-1]
    res = llm.invoke([SYSTEM_PROMPT, msg])
    return {"route": "writer", "messages": [res]}

@writes("draft")
@llm_call(model="gpt-4o-mini", reads=["messages"], static_vars=[])
def writer(state: State):
    msg = state.get("messages")
    res = llm.invoke(msg)
    return {"draft": str(res)}

workflow = StateGraph(State)
G = GraphProxy(workflow)
G.add_node("router", router)
G.add_node("writer", writer)
G.set_entry_point("router")
G.add_edge("router", "writer")
G.set_finish_point("writer")
graph = G.materialize().compile()
