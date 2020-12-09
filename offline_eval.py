import argparse
import pathlib
import importlib

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, required=True)
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    for player_code_path in pathlib.Path(args.path).glob('*.py'):
        player_code_path = str(player_code_path).replace('/', '.')
        print(f'Loading agent from {player_code_path}')
        player = importlib.import_module(player_code_path).CustomCoMaze

    