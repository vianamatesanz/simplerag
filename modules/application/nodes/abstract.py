"""
Main abstract class to define the inheritance of other nodes
"""

from abc import ABC, abstractmethod

class BaseNode(ABC):
    '''
    Main abstract class.
    '''

    @abstractmethod
    def invoke(self, state):
        '''
        Invoke method.

        :param state: The state of the graph.
        :type state: dict
        '''
        pass