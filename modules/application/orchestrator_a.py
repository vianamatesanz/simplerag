"""
This is the orchestator module where laggraph flow is created.
"""

# Import libraries
from modules.application.nodes import AgentNode, GenerateNode, GradeDocumentsNode, RewriteNode, ChangeQuestionNode, SuggestedQuestionsNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel

from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition
from langgraph.graph import END, StateGraph, START
   

class Orchestrator:
    '''
    Orchestator class to create langgraph flow.
    '''
    def __init__(self, retriever_tool, prompts, model: BaseChatModel, config_params: dict):
        '''
        Init function.

        :param retriever_tool: The tool to make the documentation retrieval.
        :type retriever_tool: LangChain Tool Function
        '''
        
        self.model = model

        self.tools = [retriever_tool]
        self.retriever_tool = retriever_tool    
        
        self.config_params = config_params

        self.prompts = prompts
        
    def _generate_nodes(self):
        '''
        Function to generate the nodes with all steps.
        '''

        nodes_cls = [AgentNode, GenerateNode, RewriteNode, ChangeQuestionNode, SuggestedQuestionsNode]
        nodes = {node.name: node(self.model, self.config_params, self.tools, self.prompts).invoke for node in nodes_cls}

        return nodes

    def _generate_conditional_edges(self):
        '''
        Function to generate conditional edges if it is necessary.
        '''
        pass
        # nodes_cond = []
        # conditional_edges = {node.name: node(self.llm, self.config_params, self.tools).invoke for node in nodes_cond}

        # return conditional_edges

    def _generate_graph(self):
        '''
        Function to generate the graph with the Graph State.
        '''

        nodes = self._generate_nodes()
        edges = self._generate_conditional_edges()
        workflow = StateGraph(GraphState)

        # Nodes
        for node_name, node in nodes.items():
            workflow.add_node(node_name, node)

        # # Edges
        # for node_name, node in edges.items():
        #     workflow.add_node(node_name, node)

        retrieve = ToolNode([self.retriever_tool])
        workflow.add_node('RetrieveNode', retrieve)
        
        # Create connection between the nodes
        workflow.add_edge(START, ChangeQuestionNode.name)
        workflow.add_edge(ChangeQuestionNode.name, AgentNode.name)

        workflow.add_conditional_edges(
            AgentNode.name,
            # Assess agent decision
            tools_condition,
            {
                # Translate the condition outputs to nodes in our graph
                'tools': 'RetrieveNode',
                END: END,
            },
        )

        grade_documents = GradeDocumentsNode(self.model, self.config_params, self.tools, self.prompts).invoke
        workflow.add_conditional_edges(
            'RetrieveNode',
            # Assess agent decision
            grade_documents,
        )

        workflow.add_edge(GenerateNode.name, SuggestedQuestionsNode.name)
        workflow.add_edge(SuggestedQuestionsNode.name, END)
        workflow.add_edge(RewriteNode.name, AgentNode.name)

        return workflow
        
    def compile(self):
        '''
        Function to compile the graph.
        '''
        graph = self._generate_graph()
        return graph.compile()
    