"""
This is the State Class for LangGraph nodes.
"""

# Import libraries
from typing import Annotated, Sequence
from typing_extensions import List, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage


class GraphState(TypedDict):
    '''
    Graph State Class.
    '''
    # The add_messages function defines how an update should be processed
    # Default is to replace. add_messages says "append"
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # Save the question in a separated variable
    question: HumanMessage
    # Save the context to extract fonts
    context: List[Document]
    # Save the suggested questions generated
    suggested_questions: str
    # Variable to measure how many times the agent is executed, so that it does not
    # exceed a fixed number
    agent_n_calls: int
    # Languages availables in the documentation
    languages: List[str]
    # Optional category to constrain retrieval (e.g. legal, informes, manuales)
    categoria: NotRequired[str]
