import random
import string
from comaze.agents import AbstractAgent


class CustomCoMaze(AbstractAgent):

    @property
    def agent_id(self) -> str:
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(4))

    def select_action(self, observation):
        direction = self.actionId2action[random.randint(0, 4)]
        symbol_message = self.id2token[random.randint(0, 10)]

        return {
            "action": {"direction": direction},
            "symbol_message": symbol_message  # optional
        }
