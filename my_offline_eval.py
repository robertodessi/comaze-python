import argparse
import importlib
import pathlib
import requests
import pickle
import time
from collections import defaultdict, namedtuple
from multiprocessing import Pool
from typing import Any, Dict, List, NamedTuple, Union
import torch
import random

from comaze.agents import AbstractAgent
#in the meantime:
#AbstractAgent = object

API_URL = "http://teamwork.vs.uni-kassel.de:16216"
WEBAPP_URL = "http://teamwork.vs.uni-kassel.de"

MAX_TIMEOUT = 10 * 60 # seconds
MAX_PROCESSES = 100

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
    
    # Now, this is where it gets complicated:
    # If the directional move proposed by the 
    # player is making the agent trying to go
    # out of the arena, then the folluwing will
    # return a JSONError that will be dealt the 
    # following way:
    # The directional move is invalid but it is
    # still the current player's turn, so we 
    # make it "SKIP".
    try:
        new_game = requests.post(request_url).json()
    except Exception as e:
        #The agent is likely trying to move outside the arena.
        # Regularising the resulting game state:
        skip_request_url = API_URL + "/game/" + game_id + "/move"
        skip_request_url += "?playerId=" + player_id
        skip_request_url += "&action=SKIP"
        new_game = requests.post(skip_request_url).json()

    print(" We have used " + str(new_game["usedMoves"]) + " moves so far.")
    print("There are " + str(len(new_game["unreachedGoals"])) + " goals left to reach.")

    return next_move


def play_one_game(agent1, agent2, game_id, agent1_name, agent2_name):
    player1 = requests.post(API_URL + "/game/" + game_id + "/attend?playerName=" + agent1_name).json()
    player2 = requests.post(API_URL + "/game/" + game_id + "/attend?playerName=" + agent2_name).json()
    print(f'Player1 id: {player1["uuid"]} joined game {game_id}')
    print(f'Player2 id: {player2["uuid"]} joined game {game_id}')

    logs = defaultdict(list)

    game = requests.get(API_URL + "/game/" + game_id).json()
    assert game["state"]["started"], f"Couldn't start game {game_id}"

    while not game["state"]["over"]:
        agent1_next_move = make_move(agent1, player1, game)
        logs[agent1_name].append(agent1_next_move)
        if game["state"]["won"]:
            break
        game = requests.get(API_URL + "/game/" + game_id).json()
        
        agent2_next_move = make_move(agent2, player2, game)
        logs[agent2_name].append(agent2_next_move)
        if game["state"]["won"]:
            break

        game = requests.get(API_URL + "/game/" + game_id).json()

    if game["state"]["won"]:
        print("Game won!")
    elif game["state"]["lost"]:
        print("Game lost (" + game["state"]["lostMessage"] + ").")

    return logs


def pair_two_agents_and_play_one_game(task) -> Union[bool, str]:

    import signal
    def timeout_handler():
        exit(0)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(MAX_TIMEOUT)
    # signal.SIGALRM will be sent in MAX_TIMEOUT seconds; handler will suicide the process by calling exit(0)


    agent1, agent2, level, rate = task
    assert level in ["1", "2", "3", "4"], f"I cannot start a game with player {agent1}, {agent2} and level {level}"

    num_of_player_slots = "2"
    if rate == 1:
        game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots +  "&actionRateLimit="  + str(rate)).json()["uuid"]
        path_ids_towatch = open(r'path_ids_towatch.txt','a')
        path_ids_towatch.write(game_id)
        path_ids_towatch.write("\n")
        path_ids_towatch.close()
        print(game_id)
        time.sleep(20)

    else:
        game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]

    logs = play_one_game(agent1.player, agent2.player, game_id, f'{agent1.team_name}_{agent1.id.split(".")[-1]}', f'{agent2.team_name}_{agent2.id.split(".")[-1]}')

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

    counter = 0
    for level in levels:
        for idx_agent1 in range(len(players)-1):
            for idx_agent2 in range(idx_agent1+1, len(players)):
                agent1 = players[idx_agent1]
                agent2 = players[idx_agent2]

                tuple_tasks.append((agent1, agent2, level, games_rates[counter]))
                counter += 1

    #threads = min(len(tuple_tasks), 36)
    #with Pool(threads) as p:
    #    games_result = p.map(pair_two_agents_and_play_one_game, tuple_tasks)
    #    p.close()
    #    p.join()

    n_processes = min(len(tuple_tasks), MAX_PROCESSES)
    with Pool(n_processes) as p:
        callback = lambda _: print("worker died")
        promised_games_result = [p.apply_async(pair_two_agents_and_play_one_game, (tuple_task,), error_callback=callback) for tuple_task in tuple_tasks]

        games_result = []
        for promise in promised_games_result:
            try:
                result = promise.get(timeout=MAX_TIMEOUT)
                games_result.append(result)
            except TimeoutError:
                games_result.append((False, "<unknown-game-id:timeout>"))
            except:
                games_result.append((False, "<unknown-game-id:died>"))
        p.close()
        # p.join() # never returns if a worker is busy forever

    for task, game_result in zip(tuple_tasks, games_result):
        agent1, agent2, level, _ = task
        level = int(level)
        game_won, game_id = game_result

        game_result = GameResult(agent1.id, agent2.id, level, game_won, game_id)
        history_dict[agent1.id].append(game_result)
        history_dict[agent2.id].append(game_result)

        if game_won:
            # final score is for 1 lev1, 3 for lev2, 5 for lev3, 7 for lev4
            performance_dict[agent1.id] += ((level * 2) -1)
            performance_dict[agent2.id] += ((level * 2) -1)

    pickle.dump(performance_dict, open( f"logging/performance_{time.strftime('%Y_%m_%d_%H_%M_%S')}.dict", "wb" ) )
    pickle.dump(history_dict, open( f"logging/history_{time.strftime('%Y_%m_%d_%H_%M_%S')}.dict", "wb" ) )
    print(*get_leaderboard(performance_dict), sep="\n")


def load_agents(path: str) -> List[Agent]:
    players = []
    for player_path in pathlib.Path(path).glob('*.player'):
        player_filename = str(player_path.with_suffix('')).replace('/', '.')

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
    logging_folder = pathlib.Path("logging")
    logging_folder.mkdir(exist_ok=True)
    players = load_agents(args.path)
    pair_all_agents_and_play_all_games(players)

    open(r'path_ids_towatch.txt','w').close() # erase file contents as all games ended


if __name__ == '__main__':
    main()
