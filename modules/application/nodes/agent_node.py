"""
This is the main Agent node that will decide if a RAG flow is necessary or not.
"""

# Import libraries
from modules.application.nodes.abstract import BaseNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel

from openai import RateLimitError, APITimeoutError, BadRequestError

import logging
import time

class AgentNode(BaseNode):
    name = 'AgentNode'

    def __init__(self, model: BaseChatModel,
                 config_params: dict, tools: list, prompts: dict):
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

        logging.info('---CALL AGENT---')

        agent_n_calls = state.get('agent_n_calls', 0) + 1

        messages = state['messages']
        languages_str = ', '.join(state['languages'])
        categoria = state.get('categoria')

        # prompt_variables = {self.prompts[AgentNode.name]['variables'][0]: languages_str}

        # system_prompt = {'role': 'system', 'content': self.prompts[AgentNode.name]['text'].format(**prompt_variables)}
        system_content = self.prompts[AgentNode.name]['text'].format(
            languages=languages_str,
            categoria=categoria or "",
        )

        # If category is provided, explicitly instruct tool usage with the category argument.
        if categoria:
            system_content += (
                "\n\nCategoria objetivo para recuperar documentos: "
                f"{categoria}. "
                "Si necesitas recuperar contexto, llama a retriever_tool "
                "incluyendo el argumento 'categoria' con ese valor."
            )

        system_prompt = {'role': 'system', 'content': system_content}

        if not (messages and messages[0].type in ('system')):
            messages.insert(0, system_prompt)

        while True:
            model = self.model.bind_tools(self.tools)
            try:
                response = model.invoke(messages)
                break
            except (RateLimitError, APITimeoutError, BadRequestError) as e:
                logging.info(e)
                time.sleep(15)
        return {'messages': [response], 'agent_n_calls': agent_n_calls}