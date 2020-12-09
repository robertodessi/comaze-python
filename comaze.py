import os
import requests
import time


class CoMaze:
  if os.path.isfile(".local"):
    API_URL = "http://localhost:16216"
    WEBAPP_URL = "http://localhost"
  else:
    API_URL = "http://teamwork.vs.uni-kassel.de:16216"
    WEBAPP_URL = "http://teamwork.vs.uni-kassel.de"
  LIB_VERSION = "1.3.0"

  def next_move(self, game, player):
    return ":("

  def play_new_game(self, options={}):
    level = options.get("level", "1")
    num_of_player_slots = options.get("num_of_player_slots", "2")
    game_id = requests.post(self.API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]
    options["game_id"] = game_id
    self.play_existing_game(options)

  def play_existing_game(self, options={}):
    print("playing existing game", options)
    if "look_for_player_name" in options:
      options["game_id"] = requests.get(self.API_URL + "/game/byPlayerName?playerName=" + options["look_for_player_name"]).json()["uuid"]

    if "game_id" not in options or len(options["game_id"]) != 36:
      raise Exception("You must provide a game id when attending an existing game. Use play_new_game() instead of play_existing_game() if you want to create a new game.")

    player_name = options.get("player_name", "Python")
    game_id = options["game_id"]
    player = requests.post(self.API_URL + "/game/" + game_id + "/attend?playerName=" + player_name).json()
    print("Joined gameId: " + game_id)
    print("Playing as playerId: " + player["uuid"])
    self.game_loop(game_id, player)

  def game_loop(self, game_id, player):
    game = requests.get(self.API_URL + "/game/" + game_id).json()

    while not game["state"]["over"]:
      game = requests.get(self.API_URL + "/game/" + game_id).json()

      while not game["state"]["started"]:
        print("Waiting for players. (Invite someone: " + self.WEBAPP_URL + "/?gameId=" + game_id + ")")
        time.sleep(3)
        continue

      while game["currentPlayer"]["uuid"] != player["uuid"]:
        print(f"Not my turn. Waiting. (should be {game['currentPlayer']['uuid']}, but I am {player['uuid']}")
        print("We have used " + str(game["usedMoves"]) + " moves so far.")
        time.sleep(0.5)
        continue

      next_move = self.next_move(game, player)

      # next_move can be a direction/skip string (maintaining compatibility with APIs <= 1.1) or a dict containing direction and an optional symbolMessage
      action = None
      symbol_message = None
      if type(next_move) == str:
        action = next_move
      elif type(next_move) == dict:
        action = next_move.get("action")
        symbol_message = next_move.get("symbol_message")

      print("Moving " + str(action))
      request_url = self.API_URL + "/game/" + game_id + "/move"
      request_url += "?playerId=" + player["uuid"]
      request_url += "&action=" + action
      if symbol_message:
        request_url += "&symbolMessage=" + symbol_message
      requests.post(request_url)

    if game["state"]["won"]:
      print("Game won!")
    elif game["state"]["lost"]:
      print("Game lost (" + game["state"]["lostMessage"] + ").")




class PairingCoMaze:
  if os.path.isfile(".local"):
    API_URL = "http://localhost:16216"
    WEBAPP_URL = "http://localhost"
  else:
    API_URL = "http://teamwork.vs.uni-kassel.de:16216"
    WEBAPP_URL = "http://teamwork.vs.uni-kassel.de"
  LIB_VERSION = "1.1.0"

  #TODO get the unique upload links somewhere!

  def next_move(self, game, player):
    return ":("

  def play_new_game(self, options={}):
    level = options.get("level", "1")
    num_of_player_slots = options.get("num_of_player_slots", "2")
    game_id = requests.post(self.API_URL + "/game/create?level=" + level + "&numOfPlayerSlots=" + num_of_player_slots).json()["uuid"]
    options["game_id"] = game_id
    self.play_existing_game(options)
    return game_id

  def play_existing_game(self, options={}):
    print("playing", options)
    if "look_for_player_name" in options:
      options["game_id"] = requests.get(self.API_URL + "/game/byPlayerName?playerName=" + options["look_for_player_name"]).json()["uuid"]

    if "game_id" not in options or len(options["game_id"]) != 36:
      raise Exception("You must provide a game id when attending an existing game. Use play_new_game() instead of play_existing_game() if you want to create a new game.")

    player_name = options.get("player_name", "Python")
    game_id = options["game_id"]
    player = requests.post(self.API_URL + "/game/" + game_id + "/attend?playerName=" + player_name).json()
    print("Joined gameId: " + game_id)
    print("Playing as playerId: " + player["uuid"])
    state = self.game_loop(game_id, player)
    if state["won"]:
      return True
    elif state["lost"]:
      return False

  def game_loop(self, game_id, player):
    game = requests.get(self.API_URL + "/game/" + game_id).json()

    while not game["state"]["over"]:
      game = requests.get(self.API_URL + "/game/" + game_id).json()

      if not game["state"]["started"]:
        print("Waiting for players. (Invite someone: " + self.WEBAPP_URL + "/?gameId=" + game_id + ")")
        time.sleep(3)
        continue

      if game["currentPlayer"]["uuid"] != player["uuid"]:
        print("Not my turn. Waiting.")
        time.sleep(1)
        continue

      direction = self.next_move(game, player)
      print("Moving " + direction)
      requests.post(self.API_URL + "/game/" + game_id + "/move?playerId=" + player["uuid"] + "&action=" + direction)

    if game["state"]["won"]:
      print("Game won!")
    elif game["state"]["lost"]:
      print("Game lost (" + game["state"]["lostMessage"] + ").")
    return game["state"]

def pairing_two(Alice, Bob):
  level = 1
  alice_perf = []
  bob_perf = []
  while level<5:
    game_id = PairingCoMaze().play_new_game({'level': level})
    alice_won = Alice.play_existing_game({"game_id":game_id})
    bob_won = Bob.play_existing_game({"game_id":game_id})
    assert not(alice_won)==bob_won
    alice_perf.append(alice_won)
    bob_perf.append(bob_won)
    level += 1
    
  return alice_perf, bob_perf


def round_robin(agents):
  saving_states = {}
  for agent in agents:
    saving_states[agent.id] = [] # TODO: agent.id not defined yet, it should be the unique upload links !!

  for agent1 in agents[:-1]:
    for agent2 in agents[1:]:
      won_1, won_2 = pairing_two(agent1, agent2)
      saving_states[agent1.id].append((agent2.id, won_1))
      saving_states[agent2.id].append((agent1.id, won_2))

  return saving_states

def evaluation(saving_states):
  scores = {}
  for agent, performances in saving_states.items():
    scores[agent]  = 0
    for level, perf in enumerate(performances[1]):
      scores[agent]+=perf*(level+1)
  return scores
