import argparse
import importlib
import pathlib
import requests
from collections import defaultdict, namedtuple
from multiprocessing import Process, Pool
from multiprocessing.pool import ThreadPool
from typing import Any, Dict, List, NamedTuple, Union

from comaze import CoMaze


API_URL = "http://teamwork.vs.uni-kassel.de:16216"
WEBAPP_URL = "http://teamwork.vs.uni-kassel.de"

"""
TODOs

- implement debug/info msgs with python logging module
"""


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, required=True)
    return parser.parse_args()


class Agent(NamedTuple):
    id: str
    team_name: str
    player: CoMaze


class GameResult(NamedTuple):
    id1: str
    id2: str
    level: int
    game_won: bool
    game_id: str


def get_leaderboard(players: Dict[str, int]):
    res = []
    for k, v in players.items():
        res.append((k, v))
    res.sort(reverse=True, key=lambda x: x[1])
    return res


def play(x):
    agent, opts = x
    return agent.play_existing_game(opts)


def pair_agents(task):
    agent1, agent2, level = task
    assert level in ["1", "2", "3", "4"], f"I cannot start a game with player {agent1}, {agent2} and level {level}"

    num_of_player_slots = "2"
    game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]

    options = {}
    options["game_id"] = game_id
    print("game id", game_id)

    opts_alice = dict(options)
    opts_alice['player_name'] = 'Alice'
    opts_bob = dict(options)
    opts_bob['player_name'] = 'Bob'

    # instantiate classes
    alice = agent1.player()
    bob = agent2.player()

    with ThreadPool(2) as p:
        p.map(play, ((alice, opts_alice), (bob, opts_bob)))
        p.close()
        p.join()
        
    game_won = requests.get(API_URL + "/game/" + game_id).json()['state']['won']
    return game_won, game_id


def pair_all_agents(players: List[Agent]):
    history_dict = defaultdict(list)

    performance_dict = {}
    for player in players:
        performance_dict[player.id] = 0

    tuple_tasks  = []

    for level in ["1"]:  # TODO extend levels
        for idx_agent1 in range(len(players)-1):
            for idx_agent2 in range(idx_agent1+1, len(players)):

                agent1 = players[idx_agent1]
                agent2 = players[idx_agent2]

                tuple_tasks.append((agent1, agent2, level))

    threads = min(len(tuple_tasks), 36)    
    with Pool(threads) as p:
        games_result = p.map(pair_agents, tuple_tasks)  
        p.close()
        p.join()

    for task, game_result in zip(tuple_tasks, games_result):
        agent1, agent2, level = task
        level = int(level)
        game_won, game_id = game_result

        game_result = GameResult(agent1.id, agent2.id, level, game_won, game_id)
        history_dict[agent1.id].append(game_result)
        history_dict[agent2.id].append(game_result)

        if game_won:
            performance_dict[agent1.id] += (1 * level)  # TODO smarter score assignment
            performance_dict[agent2.id] += (1 * level)  # TODO smarter score assignment

    print(*get_leaderboard(performance_dict), sep="\n")


def load_agents(path: str) -> List[Agent]:
    players = []
    for player_code_path in pathlib.Path(path).glob('*.py'):
        player_code_path = str(player_code_path.with_suffix('')).replace('/', '.')

        # TODO fix filenames in agent/ and make sure we split bases on dots rather than hyphens
        # TODO an agent name now also contains its dot-separated absolute path
        # a simple player_name.split(".")[-1] would do it but can't test it now

        # assuming hyphen delimits id and team_name, it's a dot in reality
        player_id = player_code_path.split('-')[0]
        team_name = player_code_path.split('-')[1]
        print(f'Loading {player_id} agent from team {team_name} from path {player_code_path}')

        player = importlib.import_module(player_code_path).CustomCoMaze
        players.append(Agent(player_id, team_name, player))

    assert len(players) > 1, "I could not load any agents from {args.path}"
    return players


def main():
    args = parse_args()

    players = load_agents(args.path)

    pair_all_agents(players)


if __name__ == '__main__':
    main()
