import argparse
import importlib
import pathlib
import requests
import pickle
import time
from collections import defaultdict, namedtuple
from multiprocessing import Process, Pool
from multiprocessing.pool import ThreadPool
from typing import Any, Dict, List, NamedTuple, Union
import torch
import random

from comaze.agents import AbstractAgent
#in the meantime:
#AbstractAgent = object

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
    player: AbstractAgent


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


def make_move(agent, player, game):
    ## agent is the participatn/user class
    ## the one we need to call the one method from
    ## player is the kson structure return by the server and associated 
    ## with the agent obj
    game_id = game["uuid"]
    player_id = player["uuid"]

    next_move = agent.select_move(game)  # this will be a call to Angelos et al's stuff
    action = next_move.get("direction")
    message = next_move.get("symbol_Message")

    print("Moving " + action)
    request_url = API_URL + "/game/" + game_id + "/move"
    request_url += "?playerId=" + player_id
    request_url += "&action=" + action
    if message:
        request_url += "&symbolMessage=" + message
    requests.post(request_url)

    print(" We have used " + str(game["usedMoves"]) + " moves so far.")
    print("There are " + str(len(game["unreachedGoals"])) + " goals left to reach.")

    return next_move


def play_one_game(agent1, agent2, game_id, agent1_name, agent2_name):
    player1 = requests.post(API_URL + "/game/" + game_id + "/attend?playerName=" + agent1_name).json()
    player2 = requests.post(API_URL + "/game/" + game_id + "/attend?playerName=" + agent2_name).json()
    print(f'Player1 id: {player1["uuid"]} joined game {game_id}')
    print(f'Player2 id: {player2["uuid"]} joined game {game_id}')

    logs = defaultdict(list)

    game = requests.get(API_URL + "/game/" + game_id).json()
    assert game["state"]["started"], f"Couldn't start game {game_id}"
    counter = 0
    while not game["state"]["over"]:
        counter  += 1
        agent1_next_move = make_move(agent1, player1, game)
        logs[player1["uuid"]].append(agent1_next_move)
        if game["state"]["won"]:
            break

        agent2_next_move = make_move(agent2, player2, game)
        logs[player2["uuid"]].append(agent2_next_move)
        if game["state"]["won"]:
            break

        game = requests.get(API_URL + "/game/" + game_id).json()

    if game["state"]["won"]:
        print("Game won!")
    elif game["state"]["lost"]:
        print("Game lost (" + game["state"]["lostMessage"] + ").")
    print('*'*10)
    print('number of moves ', counter)
    print('*'*10)
    return logs


def pair_two_agents_and_play_one_game(task) -> Union[bool, str]:
    agent1, agent2, level, rate = task
    assert level in ["1", "2", "3", "4"], f"I cannot start a game with player {agent1}, {agent2} and level {level}"

    num_of_player_slots = "2"
    if rate == 1:
        game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots +  "&actionRateLimit="  + str(rate)).json()["uuid"]
        path_ids_towatch = open(r'path_ids_towatch.txt','a') 
        path_ids_towatch.write(game_id)
        path_ids_towatch.close()

    else:
        game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"] 

    # instantiate classes
    alice = agent1.player
    bob = agent2.player

    logs = play_one_game(alice, bob, game_id, 'alice', 'bob')

    game_won = requests.get(API_URL + "/game/" + game_id).json()['state']['won']

    # save logs
    pickle.dump(logs, open( f"logging/{game_id}.p", "wb" ) )    
    return game_won, game_id


def pair_all_agents_and_play_all_games(players: List[Agent]):
    history_dict = defaultdict(list)

    performance_dict = {}
    for player in players:
        performance_dict[player.id] = 0

    levels = ["1", "2", "3", "4"]
    tuple_tasks  = []
    # chosse randomly 'to_watch' instances with a actionRateLimit of 1 to show to participants
    nbr_games = int(len(levels) * ((len(players)*(len(players)-1))/2))
    to_watch = 4
    games_rates = [0]*(nbr_games-to_watch) + [1]*to_watch
    random.shuffle(games_rates)

    counter =  0
    for level in levels:
        for idx_agent1 in range(len(players)-1):
            for idx_agent2 in range(idx_agent1+1, len(players)):
                agent1 = players[idx_agent1]
                agent2 = players[idx_agent2]

                tuple_tasks.append((agent1, agent2, level, games_rates[counter]))
                counter += 1

    threads = min(len(tuple_tasks), 36)
    #with Pool(threads) as p:
    #    games_result = p.map(pair_two_agents_and_play_one_game, tuple_tasks)
    #    p.close()
    #    p.join()   
    games_result = pair_two_agents_and_play_one_game(tuple_tasks[0])

    for task, game_result in zip(tuple_tasks, games_result):
        agent1, agent2, level, _ = task
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
    for player_path in pathlib.Path(path).glob('*.player'):
        player_filename = str(player_path.with_suffix('')).replace('/', '.')

        # TODO fix filenames in agent/ and make sure we split bases on dots rather than hyphens
        # TODO an agent name now also contains its dot-separated absolute path
        # a simple player_name.split(".")[-1] would do it but can't test it now

        # assuming hyphen delimits id and team_name, it's a dot in reality
        player_id = player_filename.split('-')[0]
        team_name = player_filename.split('-')[1]
        print(player_filename)

        try:
            print(f'Loading {player_id} agent from team {team_name} from path {player_filename}')
            player = pickle.load(open(player_path, 'rb'))
            players.append(Agent(player_id, team_name, player))
        except:
            print(f'cannot load agent from path {player_filename}')

    assert len(players) > 1, f"I could not load any agents from {path}"
    return players


def main():
    args = parse_args()
    players = load_agents(args.path)
    pair_all_agents_and_play_all_games(players)

    open(r'path_ids_towatch.txt','w').close() # erase file contents as all games ended




if __name__ == '__main__':
    main()
