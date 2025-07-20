from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uuid
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

games = {}
connections = {}

# --- Game Data (for demo, expand as needed) ---
CLASSES = {
    "Warrior": ["Berserker", "Titan"],
    "Paladin": ["Oath of Conquest", "Oath of Protection"],
    "Cleric": ["God Fearing", "War Cleric"],
    "Priest": ["Savior", "Combat Medic"],
    "Mage": ["Dragon Mage", "Chronomancer"],
    "Ranger": ["Beast Master", "Deadshot"]
}
STARTING_STATS = {"Str": 15, "Con": 14, "Wis": 13, "Int": 12}
STARTING_SPELLS = {
    "Warrior": ["Taunt", "Defend"],
    "Paladin": ["Divine Smite", "Lay on Hands"],
    "Cleric": ["Guiding Bolt", "Bane"],
    "Priest": ["Bless", "Healing Word"],
    "Mage": ["Magic Missile", "Fireball"],
    "Ranger": ["Hunter’s Mark", "Volley"]
}
STARTING_WEAPON = {
    "Warrior": "Iron Greatsword",
    "Paladin": "Iron Longsword",
    "Cleric": "Wooden Mace",
    "Priest": "Simple Staff",
    "Mage": "Basic Wand",
    "Ranger": "Wooden Shortbow"
}

def next_player(players, current):
    idx = players.index(current)
    return players[(idx + 1) % len(players)]

@app.post("/create_room")
def create_room():
    room_id = str(uuid.uuid4())[:8]
    games[room_id] = {
        "players": {},
        "player_order": [],
        "state": {
            "turn": None,
            "actions": [],
            "grid": [[None for _ in range(6)] for _ in range(6)],
            "enemies": {},
            "shop": [],
            "loot": [],
            "round": 1
        }
    }
    connections[room_id] = []
    return {"room_id": room_id}

@app.post("/join_room/{room_id}")
def join_room(room_id: str, player: str, player_class: str = None, subclass: str = None):
    if room_id not in games:
        return {"error": "Room not found"}
    if player not in games[room_id]["players"]:
        # On first join, require class/subclass selection
        if not player_class or not subclass:
            return {
                "error": "Class and subclass required",
                "classes": CLASSES
            }
        games[room_id]["players"][player] = {
            "name": player,
            "class": player_class,
            "subclass": subclass,
            "level": 1,
            "xp": 0,
            "stats": dict(STARTING_STATS),
            "inventory": [],
            "spells": list(STARTING_SPELLS.get(player_class, [])),
            "weapon": STARTING_WEAPON.get(player_class, ""),
            "gold": 0,
            "hp": 10,
            "pos": (5, len(games[room_id]["players"]) + 1)
        }
        games[room_id]["player_order"].append(player)
    if games[room_id]["state"]["turn"] is None:
        games[room_id]["state"]["turn"] = games[room_id]["player_order"][0]
    return {
        "ok": True,
        "players": list(games[room_id]["players"].keys()),
        "player_data": games[room_id]["players"][player]
    }

@app.websocket("/ws/{room_id}/{player}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player: str):
    await websocket.accept()
    if room_id not in connections:
        connections[room_id] = []
    connections[room_id].append(websocket)
    try:
        # Send initial state
        await websocket.send_json(full_state(room_id))
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "action":
                if games[room_id]["state"]["turn"] != player:
                    await websocket.send_json({"error": "Not your turn"})
                    continue
                action = data["action"]
                games[room_id]["state"]["actions"].append({"player": player, "action": action})
                # --- Example: Move logic ---
                if "move" in action:
                    pos = games[room_id]["players"][player]["pos"]
                    if action["move"] == "up":
                        games[room_id]["players"][player]["pos"] = (max(0, pos[0] - 1), pos[1])
                    elif action["move"] == "down":
                        games[room_id]["players"][player]["pos"] = (min(5, pos[0] + 1), pos[1])
                    elif action["move"] == "left":
                        games[room_id]["players"][player]["pos"] = (pos[0], max(0, pos[1] - 1))
                    elif action["move"] == "right":
                        games[room_id]["players"][player]["pos"] = (pos[0], min(5, pos[1] + 1))
                # --- Example: Inventory logic ---
                if "add_item" in action:
                    games[room_id]["players"][player]["inventory"].append(action["add_item"])
                # --- Example: Spell logic ---
                if "spell" in action:
                    spell = action["spell"]
                    target = action.get("target")
                    # Add spell effect logic here
                # --- End turn ---
                games[room_id]["state"]["turn"] = next_player(games[room_id]["player_order"], player)
                # Broadcast new state to all
                for conn in connections[room_id]:
                    await conn.send_json(full_state(room_id))
    except WebSocketDisconnect:
        connections[room_id].remove(websocket)

def full_state(room_id):
    # Compose a full state dict for clients
    g = games[room_id]
    state = {
        "players": g["players"],
        "player_order": g["player_order"],
        "turn": g["state"]["turn"],
        "actions": g["state"]["actions"],
        "grid": g["state"]["grid"],
        "enemies": g["state"]["enemies"],
        "shop": g["state"]["shop"],
        "loot": g["state"]["loot"],
        "round": g["state"]["round"]
    }
    return state
