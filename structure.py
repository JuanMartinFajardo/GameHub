import copy

class GameState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GameState, cls).__new__(cls)
            # Inicializa aquí las variables de tu juego
            cls._instance.global_variables = {}  # dictionary to hold global variables
            cls._instance.variable_permissions = {} # dictionary to hold permissions for accessing variables (e.g: 'card': ['player1', 'player2'])
            cls._instance.player_categories = []
            cls._instance.players = []
            cls._instance.current_node = None
        return cls._instance

    def update_global_variables(self, key, value):
        self.global_variables[key] = value
    
    def update_variable_permissions(self, key, players):
        self.variable_permissions[key] = players

    def update_current_node(self, node):
        self.current_node = node
    
    def update_game_state(self, modifications):
        if 'variables_to_update' in modifications:
            for key, value in modifications['variables_to_update'].items():
                self.update_global_variables(key, value)
        if 'permissions_to_update' in modifications:
            for key, players in modifications['permissions_to_update'].items():
                self.update_variable_permissions(key, players)
    
    def add_player_category(self, category):
        self.player_categories.append(category)
    
    def add_player(self, player):
        self.players.append(player)
    
    def update_history(self):
        copy.deepcopy(self.__dict__)


state = GameState('game_state') # create a singleton instance of GameState
game_history = [] # list of actions taken in the game, in order. Each element is a tuple (player, action)


class Player:
    def __init__(self, id):
        self.id = id

    def category(self):
        for category in state.player_categories:
            categories = []
            if self in category.players: 
                categories.append(category.id)
        return categories


class Player_Category: #For example, a category could be a team, or a role. In chess they are 'white' and 'black'. For Each category would have different permissions for taking actions.
    def __init__(self, id):
        self.id = id
        self.players = [] # list of players in this category
    
    def add_player(self, player):
        self.players.append(player)
    
    def remove_player(self, player):
        self.players.remove(player)


class Action:
    def __init__(self, id, end):
        self.id = id 
        self.end = end # the node this action leads to the end of the game
        self.action_parameters = {} # a dictionary to hold any extra variables that are needed for the action (e.g: in a card game, the card that is being played)         
        self.modification_function = None # a function that modifies the GameState when this action is taken (it depends on the current game state, players, and extra variables). The output is a dictionary {'variables_to_update': {'key': value}, 'permissions_to_update': {'key': [players]}}. The first one is used to update the global variables and the second one is used to update the permissions for accessing variables.
        self.multiplayer = False # if true, this action can be taken by multiple players at the same time. In this case, the action takes place when all the available players have taken their actions. If false, the action takes place when a single player takes an action. In this case, the order of the players in the list self.players determines the order in which they can take actions.

class Node:
    def __init__(self, id):
        self.id = id
        self.sequential = False # if false, the action takes place when all the available players have taken their actions. If true, the action takes place when a single player takes an action. In this case, the order of the players in the list self.players determines the order in which they can take actions.
        self.actions = []              # actions that can be taken from this node
        self.players = []              # players that can take actions in this node.
        self.action_activation_functions = {} # functions that determine when an action is available. The key is the id of the action and the value is a function that takes as input the GameState, the player and extra variables and returns a boolean. If it returns true, the action is available for that player in this node.
        self.players_activation_functions = {} # functions that determine when a player can take actions in this node. The key is the id of the player and the value is a function that takes the GameState as input and returns a boolean. If it returns true, the player can take actions in this node.
        self.terminal = False # if true, the game ends when reaching this node


    def add_action(self, action, activation_function=None):
        self.actions.append(action)
        self.action_activation_functions[action.id] = activation_function
    
    def add_player(self, player, activation_function=None):
        self.players.append(player)
        self.players_activation_functions[player.id] = activation_function

    def apply_action(self, actions, players, parameters): #MODIFY THIS FUNCTION TO ACCEPT PARAMETERS
        for player in players:
            if self.action_activation_functions[action.id](state, player) and self.players_activation_functions[player.id](state):
                state.update_game_state(action.modification_function(state))
                state.update_current_node(action.end)
                return True
            else:
                raise Exception("Action or player not available in this node")




class Flowchart:
    def __init__(self, id):
        self.id = id
        self.nodes = []
        self.actions = []

    def add_node(self, node):
        self.nodes.append(node)

    def add_action(self, action):
        self.actions.append(action)


def get_action(player):
    # Here you would implement the logic to get the action and parameters input from the player. This could be done through a user interface, command line input, or any other method of interaction. The function should return the chosen action and any necessary parameters for that action.
    action = 1
    parameters = {}
    return action, parameters


def run_game():
    while True:
        current_node = state.current_node
        if current_node.terminal:
            print("Game over")
            break
        if not current_node.sequential:
            for player in current_node.players:
                action, parameters = get_action(player)
                if current_node.players_activation_functions[player.id](state):
                    available_actions = [action for action in current_node.actions if current_node.action_activation_functions[action.id](state, player)]
                   