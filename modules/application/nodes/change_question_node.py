"""
This is the node to change the question at the beginning of the process if it necessary
to enhance the RAG search.
"""

# Import libraries
from modules.application.nodes.abstract import BaseNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from openai import BadRequestError, RateLimitError, APITimeoutError

import logging
import time

class ChangeQuestionNode(BaseNode):
    name = 'ChangeQuestionNode'

    def __init__(self, model: BaseChatModel,
                 config_params: dict, 
                 tools: list, 
                 prompts: dict):
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

        logging.info('---CHANGE QUESTION---')

        human_messages = [
            message
            for message in state['messages']
            if message.type in ('human')
        ]

        question = human_messages[-1].content

        # Prompt
        prompt = PromptTemplate(
            template = self.prompts[ChangeQuestionNode.name]['text'],
            # input_variables = self.prompts[ChangeQuestionNode.name]['variables'],
            input_variables = ['question']
        )

        # Chain
        while True:
            chain = prompt | self.model | StrOutputParser()
            try:
                response = chain.invoke({'question': question})
                break
            except (BadRequestError, RateLimitError, APITimeoutError) as e:
                logging.info(e)
                time.sleep(15)
            except ValueError as e:
                logging.info(e)
                response = question
                break
        
        messages = state['messages']

        for i in range(len(messages) - 1, -1, -1):
            if messages[i].type == 'human':
                messages[i] = HumanMessage(response)
                break

        return {'messages': messages, 'question': HumanMessage(response)}


