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
from langchain_core.output_parsers import PydanticOutputParser

import logging
import time
from pydantic import BaseModel, Field
from typing import List

class SuggestedQuestions(BaseModel):
    """Suggested questions list."""

    suggested_questions: List[str] = Field(description = 'Suggested questions list.')

class SuggestedQuestionsNode(BaseNode):
    name = 'SuggestedQuestionsNode'

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

        # Set up a parser
        parser = PydanticOutputParser(pydantic_object = SuggestedQuestions)

        messages = state['messages']
        
        question = state['question'].content
        last_message = messages[-1]

        recent_tool_messages = []
        for message in reversed(state['messages']):
            if message.type == 'tool':
                recent_tool_messages.append(message)
            else:
                break

        docs = last_message.content

        # Prompt
        prompt_suggested_questions = PromptTemplate(
            template = self.prompts[SuggestedQuestionsNode.name]['text'] + "\n\n{format_instructions}",
            input_variables = ['context', 'question'],
        )

        format_instructions = parser.get_format_instructions()

        # Chain
        while True:
            suggested_questions_chain = prompt_suggested_questions | self.model | parser
            try:
                suggested_questions = suggested_questions_chain.invoke({'context': docs, 'question': question, 'format_instructions': format_instructions})
                break
            except (BadRequestError, RateLimitError, APITimeoutError) as e:
                logging.info(e)
                time.sleep(15)
        return {'suggested_questions': suggested_questions.suggested_questions}