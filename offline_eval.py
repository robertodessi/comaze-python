import argparse
import pathlib
import importlib
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

    players = []
    for player_code_path in pathlib.Path(args.path).glob('*.py'):
        player_code_path = str(player_code_path.with_suffix('')).replace('/', '.')
        print(f'Loading agent from {player_code_path}')
        player = importlib.import_module(player_code_path).CustomCoMaze
        players.append(player)


    assert len(players) > 1

    alice, bob = players[:2]
    # instantiate classes
    alice = alice()
    bob = bob()


    level = "1" 
    num_of_player_slots = "2"
    game_id = requests.post(API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]
    options = {}
    options["game_id"] = game_id
    print("game id", game_id)

    run_alice = lambda: alice.play_existing_game(options)
    run_bob = lambda: bob.play_existing_game(options)

    jobs = []
    for r in [run_alice, run_bob]:
        p = Process(target=r)
        p.start()
        jobs.append(p)

    for p in jobs:
        p.join(timeout=60)



