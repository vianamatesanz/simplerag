"""
This is the main module to generate the final answer.
"""

# Import libraries
from modules.application.nodes.abstract import BaseNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from openai import BadRequestError, RateLimitError, APITimeoutError

import logging
import time

class GenerateNode(BaseNode):
    name = 'GenerateNode'

    def __init__(self, model: BaseChatModel, config_params: dict, tools: list, prompts: dict):
        '''
        Init function.

        :param model: BaseChatModel instance.
        :type model: BaseChatModel
        :param config_params: Config parameters.
        :type config_params: dict
        :param tools: List of tools that the agent can use.
        :type tools: list
        '''

        self.model = model
        self.config_params = config_params
        self.tools = tools
        self.prompts = prompts

    def invoke(self, state: GraphState):
        '''
        Invoke function.

        :param state: The state of the graph.
        :type state: dict
        '''

        logging.info('---GENERATE---')

        messages = state['messages']

        hist_messages = '\n'.join([
            message.content
            for message in state['messages']
            if message.type in ('human', 'ai')
        ])
        
        question = state['question'].content
        last_message = messages[-1]

        print(f"MESSAGES: {state['messages']}")

        recent_tool_messages = []
        for message in reversed(state['messages']):
            if message.type == 'tool':
                recent_tool_messages.append(message)
            else:
                break
        tool_messages = recent_tool_messages[::-1]

        docs = last_message.content

        print(f'DOCS: {docs}')

        context = []
        for tool_message in tool_messages:
            context.extend(tool_message.artifact)

        # Prompt
        prompt = PromptTemplate(
            template = self.prompts[GenerateNode.name]['text'],
            # input_variables = self.prompts[GenerateNode.name]['variables'],
            input_variables = ['question', 'context', 'hist_messages']
        )

        # Chain
        while True:
            rag_chain = prompt | self.model | StrOutputParser()
            try:
                response = rag_chain.invoke({'question': question, 'context': context, 'hist_messages': hist_messages})
                break
            except (BadRequestError, RateLimitError, APITimeoutError) as e:
                logging.info(e)
                time.sleep(15)
        return {'messages': [response], 'context': context}