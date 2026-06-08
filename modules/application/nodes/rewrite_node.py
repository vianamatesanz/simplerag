"""
This is the node to rewrite the question in the case the docs are not relevant to give a good answer.
"""

# Import libraries
from modules.application.nodes.abstract import BaseNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel

from langchain_core.messages import HumanMessage, RemoveMessage
from openai import BadRequestError, RateLimitError, APITimeoutError

import logging
import time

class RewriteNode(BaseNode):
    name = 'RewriteNode'

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

        logging.info('---REWRITE QUERY---')

        question = state['question'].content

        hist_messages = '\n'.join([
            message.content
            for message in state['messages']
            if message.type in ('human', 'ai')
        ])

        # prompt_variables = {self.prompts[RewriteNode.name]['variables'][0]: question,
        #                     self.prompts[RewriteNode.name]['variables'][1]: hist_messages}

        prompt_rewrite = self.prompts[RewriteNode.name]['text'].format(question = question, hist_messages = hist_messages)

        msg = [
            HumanMessage(
                content = prompt_rewrite
            )
        ]

        # Grader
        while True:
            try:
                response = self.model.invoke(msg)
                break
            except (BadRequestError, RateLimitError, APITimeoutError) as e:
                logging.info(e)
                time.sleep(15)
            except ValueError as e:
                logging.info(e)
                response = question
                break
        
        # Remove previous messages if the message has been rewrited
        delete_messages = [RemoveMessage(id = m.id) for m in state['messages']]
        
        return {'messages': delete_messages + [HumanMessage(content = response.content)]}