"""
This is the node for grading documents relevance in order to determina whether the answer can be found in the content.
"""

# Import libraries
from modules.application.nodes.abstract import BaseNode
from modules.application.state import GraphState
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from openai import BadRequestError, RateLimitError, APITimeoutError

from typing import Literal
import time
from pydantic import BaseModel, Field
import logging

class GradeDocumentsNode(BaseNode):
    name = 'GradeDocumentsNode'

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

    def invoke(self, state: GraphState) -> Literal['GenerateNode', 'RewriteNode']:
        '''
        Invoke function.

        :param state: The state of the graph.
        :type state: dict
        '''

        logging.info('---CHECK RELEVANCE---')

        # Data model
        class clase_puntuacion_binaria(BaseModel):
            """Puntuacion binaria para la verificación de la relevancia"""

            punt_binaria: str = Field(description = "Puntuació binària 'sí' o 'no'")

        # LLM
        while True:
            llm_with_tool = self.model.with_structured_output(clase_puntuacion_binaria)
            prompt = PromptTemplate(
                template=self.prompts[GradeDocumentsNode.name]['text'],
                input_variables = ['context', 'question']
            )
            chain = prompt | llm_with_tool
            messages = state['messages']
            last_message = messages[-1]
            question = state['question'].content
            docs = last_message.content
            try:
                scored_result = chain.invoke({'question': question, 'context': docs})
                break
            except (BadRequestError, RateLimitError, APITimeoutError) as e:
                logging.info(e)
                time.sleep(15)
                scored_result.punt_binaria = 'sí'
                break
            except RateLimitError as e:
                logging.info(e)
                time.sleep(15)
            except APITimeoutError as e:
                logging.info(e)
                time.sleep(50)
            except ValueError as e:
                logging.info(e)
                # scored_result = {'punt_binaria': 'sí'}
                scored_result.punt_binaria = 'sí'
                break

        # score = scored_result['punt_binaria']
        score = scored_result.punt_binaria

        if score == 'sí' or state['agent_n_calls'] > 5:
            logging.info('---DECISION: DOCS RELEVANT---')
            return 'GenerateNode'

        else:
            logging.info('---DECISION: DOCS NOT RELEVANT---')
            return 'RewriteNode'