from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
import uuid
import random

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
SPELL_RANGES = {
    "Fireball": 3,
    "Magic Missile": 4,
    "Lay on Hands": 1,
    "Healing Word": 3,
    "Guiding Bolt": 3,
    "Bless": 3,
    "Taunt": 2,
    "Defend": 0
}
SHOP_ITEMS = [
    {"name": "Potion", "price": 10},
    {"name": "Iron Sword", "price": 50},
    {"name": "Scroll", "price": 30}
]
ENCOUNTER_TABLE = [
    {"name": "Goblin Ambush", "enemies": {"Goblin": {"pos": (0, 2), "hp": 10}, "Goblin2": {"pos": (0, 3), "hp": 10}}},
    {"name": "Orc Patrol", "enemies": {"Orc": {"pos": (0, 2), "hp": 15}, "Goblin": {"pos": (1, 2), "hp": 10}}},
    {"name": "Shaman's Circle", "enemies": {"Shaman": {"pos": (0, 2), "hp": 12}, "Goblin": {"pos": (1, 2), "hp": 10}, "Berserker": {"pos": (0, 3), "hp": 14}}},
    {"name": "Dragon's Lair", "enemies": {"Dragon": {"pos": (0, 2), "hp": 50}}}
]

def next_player(players, current):
    idx = players.index(current)
    return players[(idx + 1) % len(players)]

def is_adjacent(pos1, pos2):
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]) == 1

def in_range(pos1, pos2, rng):
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]) <= rng

def build_grid(players, enemies):
    grid = [[None for _ in range(6)] for _ in range(6)]
    for pname, pdata in players.items():
        if pdata["hp"] > 0:
            r, c = pdata["pos"]
            grid[r][c] = f"P:{pname[:2]}"
    for ename, edata in enemies.items():
        if edata["hp"] > 0:
            r, c = edata["pos"]
            grid[r][c] = f"E:{ename[:2]}"
    return grid

def get_loot(player_class):
    loot_options = ["Potion", "Gold", "Scroll", "Iron Sword", "Mana Crystal"]
    return random.choice(loot_options)

def enemy_turn(room_id):
    state = games[room_id]["state"]
    players = games[room_id]["players"]
    enemies = state["enemies"]
    for ename, edata in list(enemies.items()):
        if edata["hp"] <= 0:
            continue
        living_players = [p for p in players.values() if p["hp"] > 0]
        if not living_players:
            break
        nearest = min(living_players, key=lambda p: abs(p["pos"][0] - edata["pos"][0]) + abs(p["pos"][1] - edata["pos"][1]))
        prow, pcol = nearest["pos"]
        erow, ecol = edata["pos"]
        # If adjacent, attack
        if abs(prow - erow) + abs(pcol - ecol) == 1:
            nearest["hp"] -= 2  # Enemy attack damage
        else:
            # Move toward player
            drow = 1 if prow > erow else -1 if prow < erow else 0
            dcol = 1 if pcol > ecol else -1 if pcol < ecol else 0
            new_row = erow + drow if 0 <= erow + drow < 6 else erow
            new_col = ecol + dcol if 0 <= ecol + dcol < 6 else ecol
            occupied = [p["pos"] for p in players.values() if p["hp"] > 0]
            occupied += [e["pos"] for e in enemies.values() if e["hp"] > 0 and e != edata]
            if (new_row, new_col) not in occupied:
                edata["pos"] = (new_row, new_col)

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
            "enemies": ENCOUNTER_TABLE[0]["enemies"].copy(),
            "encounter": 0,
            "encounter_name": ENCOUNTER_TABLE[0]["name"],
            "shop": SHOP_ITEMS.copy(),
            "round": 1,
            "winner": None
        }
    }
    connections[room_id] = []
    return {"room_id": room_id}

@app.post("/join_room/{room_id}")
def join_room(
    room_id: str,
    player: str = Query(...),
    player_class: str = Query(None),
    subclass: str = Query(None)
):
    if room_id not in games:
        return {"error": "Room not found"}
    if player not in games[room_id]["players"]:
        if not player_class or not subclass:
            return {
                "error": "Class and subclass required",
                "classes": CLASSES
            }
        pos = (5, len(games[room_id]["players"]) + 1)
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
            "gold": 100,
            "hp": 10,
            "pos": pos,
            "status": [],
            "achievements": []
        }
        games[room_id]["player_order"].append(player)
    if games[room_id]["state"]["turn"] is None:
        games[room_id]["state"]["turn"] = games[room_id]["player_order"][0]
    games[room_id]["state"]["grid"] = build_grid(games[room_id]["players"], games[room_id]["state"]["enemies"])
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
        await websocket.send_json(full_state(room_id))
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "action":
                if games[room_id]["state"]["turn"] != player or games[room_id]["state"]["winner"]:
                    await websocket.send_json({"error": "Not your turn or game over"})
                    continue
                action = data["action"]
                games[room_id]["state"]["actions"].append({"player": player, "action": action})
                # --- Move logic ---
                if "move" in action:
                    direction = action["move"]
                    prow, pcol = games[room_id]["players"][player]["pos"]
                    new_pos = {
                        "up": (max(0, prow - 1), pcol),
                        "down": (min(5, prow + 1), pcol),
                        "left": (prow, max(0, pcol - 1)),
                        "right": (prow, min(5, pcol + 1))
                    }[direction]
                    occupied = [p["pos"] for p in games[room_id]["players"].values() if p["hp"] > 0 and p["name"] != player]
                    occupied += [e["pos"] for e in games[room_id]["state"]["enemies"].values()]
                    if new_pos not in occupied:
                        games[room_id]["players"][player]["pos"] = new_pos
                # --- Attack logic ---
                if "attack" in action:
                    target = action["attack"]
                    if target in games[room_id]["state"]["enemies"]:
                        ppos = games[room_id]["players"][player]["pos"]
                        epos = games[room_id]["state"]["enemies"][target]["pos"]
                        if is_adjacent(ppos, epos):
                            games[room_id]["state"]["enemies"][target]["hp"] -= 3
                            if games[room_id]["state"]["enemies"][target]["hp"] <= 0:
                                del games[room_id]["state"]["enemies"][target]
                # --- Spell logic (AoE for Fireball) ---
                if "spell" in action:
                    spell = action["spell"]
                    target = action.get("target")
                    rng = SPELL_RANGES.get(spell, 3)
                    if spell == "Fireball" and target in games[room_id]["state"]["enemies"]:
                        ppos = games[room_id]["players"][player]["pos"]
                        epos = games[room_id]["state"]["enemies"][target]["pos"]
                        if in_range(ppos, epos, rng):
                            for ename, edata in list(games[room_id]["state"]["enemies"].items()):
                                if in_range(epos, edata["pos"], 1):
                                    edata["hp"] -= 5
                                    if edata["hp"] <= 0:
                                        del games[room_id]["state"]["enemies"][ename]
                    if spell == "Heal" and target in games[room_id]["players"]:
                        ppos = games[room_id]["players"][player]["pos"]
                        tpos = games[room_id]["players"][target]["pos"]
                        if in_range(ppos, tpos, rng):
                            games[room_id]["players"][target]["hp"] += 5
                # --- Use item ---
                if "use_item" in action:
                    item = action["use_item"]
                    if item in games[room_id]["players"][player]["inventory"]:
                        if item == "Potion":
                            games[room_id]["players"][player]["hp"] += 5
                        games[room_id]["players"][player]["inventory"].remove(item)
                # --- Trade ---
                if "trade" in action:
                    item = action["trade"]["item"]
                    to_player = action["trade"]["to"]
                    if item in games[room_id]["players"][player]["inventory"]:
                        games[room_id]["players"][player]["inventory"].remove(item)
                        games[room_id]["players"][to_player]["inventory"].append(item)
                # --- Give gold ---
                if "give_gold" in action:
                    amount = action["give_gold"]["amount"]
                    to_player = action["give_gold"]["to"]
                    if games[room_id]["players"][player]["gold"] >= amount:
                        games[room_id]["players"][player]["gold"] -= amount
                        games[room_id]["players"][to_player]["gold"] += amount
                # --- Buy ---
                if "buy" in action:
                    item = action["buy"]
                    for shop_item in games[room_id]["state"]["shop"]:
                        if shop_item["name"] == item and games[room_id]["players"][player]["gold"] >= shop_item["price"]:
                            games[room_id]["players"][player]["gold"] -= shop_item["price"]
                            games[room_id]["players"][player]["inventory"].append(item)
                            break
                # --- Sell ---
                if "sell" in action:
                    item = action["sell"]
                    if item in games[room_id]["players"][player]["inventory"]:
                        price = next((i["price"] for i in games[room_id]["state"]["shop"] if i["name"] == item), 10) // 2
                        games[room_id]["players"][player]["gold"] += price
                        games[room_id]["players"][player]["inventory"].remove(item)
                # --- XP/Level logic ---
                if "gain_xp" in action:
                    xp = action["gain_xp"]
                    pdata = games[room_id]["players"][player]
                    pdata["xp"] += xp
                    if pdata["xp"] >= 100:
                        pdata["level"] += 1
                        pdata["xp"] = 0
                        pdata["stats"]["Str"] += 1
                        pdata["stats"]["Con"] += 1
                        if pdata["class"] == "Mage" and "Lightning Bolt" not in pdata["spells"]:
                            pdata["spells"].append("Lightning Bolt")
                        if pdata["level"] == 3:
                            pdata["weapon"] = "Steel Sword"
                # --- Status effects ---
                if "apply_status" in action:
                    effect = action["apply_status"]
                    games[room_id]["players"][player].setdefault("status", []).append(effect)
                # --- End turn ---
                # Check win/lose
                if all(p["hp"] <= 0 for p in games[room_id]["players"].values()):
                    games[room_id]["state"]["winner"] = "enemies"
                elif not games[room_id]["state"]["enemies"]:
                    for pname, pdata in games[room_id]["players"].items():
                        loot = get_loot(pdata["class"])
                        pdata["inventory"].append(loot)
                    if games[room_id]["state"]["encounter"] == 1:
                        games[room_id]["state"]["shop"].append({"name": "Steel Sword", "price": 100})
                    if games[room_id]["state"]["encounter"] == 2:
                        games[room_id]["state"]["shop"].append({"name": "Legendary Amulet", "price": 300})
                    games[room_id]["state"]["encounter"] += 1
                    if games[room_id]["state"]["encounter"] < len(ENCOUNTER_TABLE):
                        encounter = ENCOUNTER_TABLE[games[room_id]["state"]["encounter"]]
                        games[room_id]["state"]["enemies"] = encounter["enemies"].copy()
                        games[room_id]["state"]["encounter_name"] = encounter["name"]
                    else:
                        games[room_id]["state"]["winner"] = "players"
                # Enemy AI turn
                if not games[room_id]["state"]["winner"]:
                    enemy_turn(room_id)
                    games[room_id]["state"]["turn"] = next_player(games[room_id]["player_order"], player)
                games[room_id]["state"]["grid"] = build_grid(games[room_id]["players"], games[room_id]["state"]["enemies"])
                for conn in connections[room_id]:
                    await conn.send_json(full_state(room_id))
    except WebSocketDisconnect:
        connections[room_id].remove(websocket)

def full_state(room_id):
    g = games[room_id]
    state = {
        "players": g["players"],
        "player_order": g["player_order"],
        "turn": g["state"]["turn"],
        "actions": g["state"]["actions"],
        "grid": g["state"]["grid"],
        "enemies": g["state"]["enemies"],
        "shop": g["state"]["shop"],
        "round": g["state"]["round"],
        "encounter": g["state"]["encounter"],
        "encounter_name": g["state"].get("encounter_name", ""),
        "winner": g["state"]["winner"]
    }
    return state
