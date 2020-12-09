import argparse
from collections import namedtuple
import importlib
import pathlib
import requests
from multiprocessing import Process



API_URL = "http://teamwork.vs.uni-kassel.de:16216"
WEBAPP_URL = "http://teamwork.vs.uni-kassel.de"

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, required=True)
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    Agent = namedtuple('Agent', ['id', 'team_name', 'player'])

    players = []
    for player_code_path in pathlib.Path(args.path).glob('*.py'):
        player_code_path = str(player_code_path.with_suffix('')).replace('/', '.')

        # assuming hyphen delimits id and team_name, it's a dot in reality
        player_id = player_code_path.split('-')[0]
        team_name = player_code_path.split('-')[1]
        print(f'Loading {player_id} agent from team {team_name} from path {player_code_path}')

        player = importlib.import_module(player_code_path).CustomCoMaze
        players.append(Agent(player_id, team_name, player))

    assert len(players) > 1

    alice, bob = players[:2]
    # instantiate classes
    alice = alice.player()
    bob = bob.player()


    level = "1"
    num_of_player_slots = "2"
    game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]
    options = {}
    options["game_id"] = game_id
    print("game id", game_id)

    opts_alice = dict(options)
    opts_alice['player_name'] = 'Alice'
    opts_bob = dict(options)
    opts_bob['player_name'] = 'Bob'

    run_alice = lambda: alice.play_existing_game(opts_alice)
    run_bob = lambda: bob.play_existing_game(opts_bob)

    jobs = []
    for r in [run_alice, run_bob]:
        p = Process(target=r)
        p.start()
        jobs.append(p)

    for p in jobs:
        p.join(timeout=60)

    game_won = requests.get(self.API_URL + "/game/" + game_id).json()['state']['won']
