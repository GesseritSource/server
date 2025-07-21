from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
import json
import random
import asyncio
from typing import Dict, List, Optional
import os

# Load JSON data
def load_json_data(filename: str) -> Dict:
    """Load JSON data from file"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {filename} not found, using fallback data")
        return {}

# Load all JSON data
SPELL_DATA = load_json_data('class_spells_level_1_to_20.json')
WEAPON_DATA = load_json_data('class_weapon_progression_by_level.json')
PASSIVE_DATA = load_json_data('class_passives_by_level.json')

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Game state storage
games: Dict[str, Dict] = {}
SAVE_DIR = 'saves'
ROOMS_FILE = 'rooms.json'

# Ensure save directory exists
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def save_rooms():
    with open(ROOMS_FILE, 'w') as f:
        json.dump(games, f, indent=2)

def load_rooms():
    global games
    if os.path.exists(ROOMS_FILE):
        with open(ROOMS_FILE, 'r') as f:
            games = json.load(f)
    else:
        games = {}

# Load rooms on startup
load_rooms()

def load_player_data(player_name: str, save_slot: int) -> Optional[Dict]:
    """Load player data from save file"""
    save_path = os.path.join(SAVE_DIR, f'save{save_slot}_{player_name}.json')
    if os.path.exists(save_path):
        try:
            with open(save_path, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_player_data(player_name: str, save_slot: int, player_data: Dict):
    """Save player data to file"""
    save_path = os.path.join(SAVE_DIR, f'save{save_slot}_{player_name}.json')
    with open(save_path, 'w') as f:
        json.dump(player_data, f, indent=2)

def create_new_player(name: str, player_class: str, subclass: str, save_slot: int) -> Dict:
    """Create a new player with default stats using JSON data"""
    # Standard array: 15, 14, 13, 12
    class_stat_priorities = {
        'Warrior': ['Str', 'Con', 'Wis', 'Int'],
        'Paladin': ['Con', 'Str', 'Wis', 'Int'],
        'Cleric': ['Wis', 'Con', 'Str', 'Int'],
        'Priest': ['Wis', 'Int', 'Con', 'Str'],
        'Mage': ['Int', 'Wis', 'Con', 'Str'],
        'Ranger': ['Str', 'Con', 'Wis', 'Int'],
    }
    
    standard_array = [15, 14, 13, 12]
    priorities = class_stat_priorities.get(player_class, ['Str', 'Con', 'Wis', 'Int'])
    attributes = {}
    for i, attr in enumerate(priorities):
        attributes[attr] = standard_array[i]
    
    # Fill missing stats with 10
    for attr in ['Str', 'Con', 'Wis', 'Int']:
        if attr not in attributes:
            attributes[attr] = 10
    
    # Get starting spells from JSON data
    spells = []
    if player_class in SPELL_DATA:
        # Get base spells for level 1
        base_spells = SPELL_DATA[player_class].get('Base', [])
        for spell in base_spells:
            if spell['level'] == 1:
                spells.append(spell['name'])
        
        # Get subclass spells for level 1
        subclass_spells = SPELL_DATA[player_class].get(subclass, [])
        for spell in subclass_spells:
            if spell['level'] == 1:
                spells.append(spell['name'])
    
    # Limit to 4 spells
    spells = spells[:4]
    
    # Get initial weapon from JSON data
    weapon = "Dagger"  # Fallback
    if player_class in WEAPON_DATA:
        level_1_weapons = WEAPON_DATA[player_class]['levels'].get('1', [])
        if level_1_weapons:
            weapon = level_1_weapons[0]['name']
    
    # Get passive from JSON data
    passive = None
    if player_class in PASSIVE_DATA:
        # Check subclass first
        if subclass in PASSIVE_DATA[player_class]:
            level_1_key = "Level 1"
            if level_1_key in PASSIVE_DATA[player_class][subclass]:
                passive = PASSIVE_DATA[player_class][subclass][level_1_key]
        
        # Check base class if no subclass passive
        if passive is None and 'Base' in PASSIVE_DATA[player_class]:
            level_1_key = "Level 1"
            if level_1_key in PASSIVE_DATA[player_class]['Base']:
                passive = PASSIVE_DATA[player_class]['Base'][level_1_key]
    
    if passive is None:
        passive = "None"
    
    return {
        'name': name,
        'player_class': player_class,
        'subclass': subclass,
        'level': 1,
        'spells': spells,
        'weapon': weapon,
        'inventory': [],
        'gold': 0,
        'save_slot': save_slot,
        'xp': 0,
        'ac': 10 + attributes.get('Con', 10),
        'attributes': attributes,
        'passive': passive,
        'hp': 10 + attributes.get('Con', 10),
        'max_hp': 10 + attributes.get('Con', 10)
    }

@app.post("/create_room")
def create_room():
    """Create a new game room"""
    room_id = f"room_{random.randint(1000, 9999)}"
    games[room_id] = {
        "players": {},
        "player_order": [],
        "state": {
            "turn": None,
            "phase": "setup",  # setup, combat, loot, shop
            "grid": [[None for _ in range(6)] for _ in range(6)],
            "player_positions": {},
            "enemies": {},
            "player_hp": {},
            "inventory": {},
            "spells": {},
            "gold": {},
            "level": {},
            "xp": {},
            "shop_items": [],
            "loot_pool": [],
            "encounter_number": 0
        }
    }
    save_rooms()
    return {"room_id": room_id}

@app.post("/join_room/{room_id}")
def join_room(
    room_id: str,
    player: str = Query(...),
    player_class: str = Query(None),
    subclass: str = Query(None),
    save_slot: int = Query(1),
    load_save: bool = Query(False)
):
    """Join a game room with player data"""
    if room_id not in games:
        return {"error": "Room not found"}
    
    # Load existing player data or create new player
    if load_save:
        player_data = load_player_data(player, save_slot)
        if player_data:
            games[room_id]["players"][player] = player_data
        else:
            return {"error": "Save file not found"}
    else:
        if not player_class or not subclass:
            return {"error": "Player class and subclass required for new characters"}
        player_data = create_new_player(player, player_class, subclass, save_slot)
        games[room_id]["players"][player] = player_data
    
    # Add to player order if not already there
    if player not in games[room_id]["player_order"]:
        games[room_id]["player_order"].append(player)
    
    # Set turn if not set
    if games[room_id]["state"]["turn"] is None and games[room_id]["player_order"]:
        games[room_id]["state"]["turn"] = games[room_id]["player_order"][0]
    
    # Update state with player data
    games[room_id]["state"]["player_hp"][player] = player_data["hp"]
    games[room_id]["state"]["inventory"][player] = player_data["inventory"]
    games[room_id]["state"]["spells"][player] = player_data["spells"]
    games[room_id]["state"]["gold"][player] = player_data["gold"]
    games[room_id]["state"]["level"][player] = player_data["level"]
    games[room_id]["state"]["xp"][player] = player_data["xp"]
    save_rooms()
    
    return {"success": True, "player_data": player_data}

@app.get("/list_saves/{player_name}")
def list_saves(player_name: str):
    """List available save slots for a player"""
    saves = []
    for i in range(1, 4):  # 3 save slots
        save_path = os.path.join(SAVE_DIR, f'save{i}_{player_name}.json')
        if os.path.exists(save_path):
            try:
                with open(save_path, 'r') as f:
                    data = json.load(f)
                    saves.append({
                        "slot": i,
                        "name": data.get("name", "Unknown"),
                        "level": data.get("level", 1),
                        "player_class": data.get("player_class", "Unknown"),
                        "subclass": data.get("subclass", "Unknown")
                    })
            except:
                continue
    return {"saves": saves}

@app.get("/get_classes")
def get_classes():
    """Get available classes and subclasses from JSON data"""
    classes = {}
    
    # Get classes and subclasses from spell data
    if SPELL_DATA:
        for class_name, subclasses in SPELL_DATA.items():
            # Filter out 'Base' and get actual subclass names
            subclass_list = [name for name in subclasses.keys() if name != 'Base']
            if subclass_list:
                classes[class_name] = subclass_list
    
    # Fallback if JSON data is not available
    if not classes:
        classes = {
            "Warrior": ["Fighter", "Barbarian"],
            "Paladin": ["Devotion", "Vengeance"],
            "Cleric": ["Life", "War"],
            "Priest": ["Light", "Knowledge"],
            "Mage": ["Evocation", "Abjuration"],
            "Ranger": ["Hunter", "Beast Master"]
        }
    
    return {"classes": classes}

def generate_encounter(encounter_number: int) -> Dict:
    """Generate enemies for an encounter using encounters.json"""
    enemies = {}
    
    # Load encounters from JSON file
    encounters = load_json_data('encounters.json')
    
    if encounters:
        # Find appropriate encounter based on difficulty
        suitable_encounters = [e for e in encounters if e['difficulty'] <= encounter_number + 1]
        if not suitable_encounters:
            suitable_encounters = encounters
        
        # Pick a random suitable encounter
        encounter = random.choice(suitable_encounters)
        
        # Convert encounter enemies to game format
        for i, enemy_data in enumerate(encounter['enemies']):
            enemy_type = enemy_data['type']
            row = enemy_data['row']
            col = enemy_data['col']
            
            # Enemy stats based on type
            enemy_stats = {
                'Goblin': {'hp': 30, 'attack': 8, 'ac': 11},
                'Orc': {'hp': 50, 'attack': 12, 'ac': 13},
                'Skeleton': {'hp': 40, 'attack': 10, 'ac': 12},
                'Bandit': {'hp': 35, 'attack': 9, 'ac': 12},
                'Troll': {'hp': 70, 'attack': 15, 'ac': 14},
                'Shaman': {'hp': 35, 'attack': 6, 'ac': 12},
                'Necromancer': {'hp': 30, 'attack': 5, 'ac': 12},
                'Healer': {'hp': 28, 'attack': 4, 'ac': 11},
                'Berserker': {'hp': 45, 'attack': 10, 'ac': 12},
                'Alchemist': {'hp': 32, 'attack': 7, 'ac': 11},
                'Witch': {'hp': 28, 'attack': 6, 'ac': 12},
                'Sniper': {'hp': 30, 'attack': 14, 'ac': 12},
                'Guardian': {'hp': 60, 'attack': 8, 'ac': 15},
                'Enchanter': {'hp': 30, 'attack': 5, 'ac': 12},
                'Dragon': {'hp': 120, 'attack': 20, 'ac': 17},
                'Lich King': {'hp': 100, 'attack': 18, 'ac': 16},
            }
            
            stats = enemy_stats.get(enemy_type, {'hp': 30, 'attack': 8, 'ac': 11})
            
            enemy = {
                "name": f"{enemy_type} {i+1}",
                "type": enemy_type.lower(),
                "hp": stats['hp'],
                "max_hp": stats['hp'],
                "damage": stats['attack'],
                "ac": stats['ac'],
                "position": [row, col]
            }
            enemies[enemy["name"]] = enemy
    else:
        # Fallback to original generation
        enemy_types = ["Goblin", "Orc", "Troll", "Dragon"]
        num_enemies = min(encounter_number + 1, 4)
        
        for i in range(num_enemies):
            enemy_type = random.choice(enemy_types)
            enemy = {
                "name": f"{enemy_type} {i+1}",
                "type": enemy_type,
                "hp": 20 + (encounter_number * 5),
                "max_hp": 20 + (encounter_number * 5),
                "damage": 5 + encounter_number,
                "ac": 12 + encounter_number,
                "position": [random.randint(0, 5), random.randint(0, 5)]
            }
            enemies[enemy["name"]] = enemy
    
    return enemies

def generate_shop_items() -> List[Dict]:
    """Generate shop items"""
    items = [
        {"name": "Health Potion", "cost": 50, "type": "consumable", "effect": "heal"},
        {"name": "Mana Potion", "cost": 50, "type": "consumable", "effect": "mana"},
        {"name": "Iron Sword", "cost": 100, "type": "weapon", "damage": 8},
        {"name": "Leather Armor", "cost": 80, "type": "armor", "ac": 2},
        {"name": "Magic Ring", "cost": 200, "type": "accessory", "effect": "buff"}
    ]
    return random.sample(items, 3)

def generate_loot() -> List[Dict]:
    """Generate loot pool"""
    loot = [
        {"name": "Gold", "amount": random.randint(10, 50)},
        {"name": "Health Potion", "type": "consumable"},
        {"name": "Magic Scroll", "type": "spell"},
        {"name": "Gem", "value": random.randint(20, 100)}
    ]
    return random.sample(loot, 2)

@app.websocket("/ws/{room_id}/{player}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player: str):
    print(f"[DEBUG] WebSocket connect attempt: room_id={room_id}, player={player}")
    print(f"[DEBUG] Current rooms: {list(games.keys())}")
    if room_id in games:
        print(f"[DEBUG] Players in room: {list(games[room_id]['players'].keys())}")
    await websocket.accept()
    if room_id not in games or player not in games[room_id]["players"]:
        print("[DEBUG] Rejecting connection: room or player not found")
        await websocket.close()
        return
    
    try:
        while True:
            # Send current game state
            state = games[room_id]["state"].copy()
            state["players"] = games[room_id]["players"]
            state["player_order"] = games[room_id]["player_order"]
            await websocket.send_text(json.dumps(state))
            
            # Wait for action from player
            if state["turn"] == player:
                data = await websocket.receive_text()
                action_data = json.loads(data)
                action = action_data.get("action", {})
                
                # Handle different action types
                if "move" in action:
                    direction = action["move"]
                    current_pos = state["player_positions"].get(player, [0, 0])
                    new_pos = current_pos.copy()
                    
                    if direction == "up" and new_pos[1] > 0:
                        new_pos[1] -= 1
                    elif direction == "down" and new_pos[1] < 5:
                        new_pos[1] += 1
                    elif direction == "left" and new_pos[0] > 0:
                        new_pos[0] -= 1
                    elif direction == "right" and new_pos[0] < 5:
                        new_pos[0] += 1
                    
                    state["player_positions"][player] = new_pos
                
                elif "attack" in action:
                    target = action["attack"]
                    if target in state["enemies"]:
                        enemy = state["enemies"][target]
                        damage = random.randint(5, 15)
                        enemy["hp"] -= damage
                        if enemy["hp"] <= 0:
                            del state["enemies"][target]
                
                elif "spell" in action:
                    spell = action["spell"]
                    target = action.get("target")
                    # Handle spell effects (simplified)
                    if spell in ["Healing Word", "Cure Wounds"]:
                        heal_amount = random.randint(10, 20)
                        state["player_hp"][player] = min(
                            state["player_hp"][player] + heal_amount,
                            games[room_id]["players"][player]["max_hp"]
                        )
                    elif spell in ["Fireball", "Magic Missile"]:
                        if target in state["enemies"]:
                            damage = random.randint(15, 25)
                            state["enemies"][target]["hp"] -= damage
                            if state["enemies"][target]["hp"] <= 0:
                                del state["enemies"][target]
                
                elif "shop" in action:
                    item_name = action["shop"]
                    player_gold = state["gold"][player]
                    for item in state["shop_items"]:
                        if item["name"] == item_name and player_gold >= item["cost"]:
                            state["gold"][player] -= item["cost"]
                            state["inventory"][player].append(item)
                            break
                
                elif "loot" in action:
                    item_name = action["loot"]
                    for item in state["loot_pool"]:
                        if item["name"] == item_name:
                            state["inventory"][player].append(item)
                            state["loot_pool"].remove(item)
                            break
                
                elif "next_phase" in action:
                    current_phase = state["phase"]
                    if current_phase == "setup":
                        # Start combat
                        state["phase"] = "combat"
                        state["encounter_number"] += 1
                        state["enemies"] = generate_encounter(state["encounter_number"])
                        # Position players randomly
                        for p in games[room_id]["player_order"]:
                            state["player_positions"][p] = [random.randint(0, 2), random.randint(0, 2)]
                    
                    elif current_phase == "combat":
                        # Check if combat is over
                        if not state["enemies"]:
                            state["phase"] = "loot"
                            state["loot_pool"] = generate_loot()
                            # Award XP and gold
                            for p in games[room_id]["player_order"]:
                                state["xp"][p] += 100
                                state["gold"][p] += random.randint(10, 30)
                    
                    elif current_phase == "loot":
                        state["phase"] = "shop"
                        state["shop_items"] = generate_shop_items()
                    
                    elif current_phase == "shop":
                        state["phase"] = "setup"
                        # Save all players
                        for p in games[room_id]["player_order"]:
                            player_data = games[room_id]["players"][p].copy()
                            player_data.update({
                                "hp": state["player_hp"][p],
                                "inventory": state["inventory"][p],
                                "gold": state["gold"][p],
                                "xp": state["xp"][p]
                            })
                            save_player_data(p, player_data["save_slot"], player_data)
                
                # Move to next player's turn
                current_turn_index = games[room_id]["player_order"].index(state["turn"])
                next_turn_index = (current_turn_index + 1) % len(games[room_id]["player_order"])
                state["turn"] = games[room_id]["player_order"][next_turn_index]
                
                # Update game state
                games[room_id]["state"] = state
                save_rooms()
                
                # Check for game over conditions
                if not state["enemies"] and state["phase"] == "combat":
                    state["winner"] = "Players"
                
                # Check if all players are dead
                alive_players = [p for p in games[room_id]["player_order"] 
                               if state["player_hp"].get(p, 0) > 0]
                if not alive_players and state["phase"] == "combat":
                    state["winner"] = "Enemies"
            
            else:
                # Wait for other player's turn
                await asyncio.sleep(1)
                
    except WebSocketDisconnect:
        # Remove player from game
        if room_id in games and player in games[room_id]["player_order"]:
            games[room_id]["player_order"].remove(player)
            if player in games[room_id]["players"]:
                del games[room_id]["players"][player]
            
            # Update turn if needed
            if games[room_id]["state"]["turn"] == player:
                if games[room_id]["player_order"]:
                    games[room_id]["state"]["turn"] = games[room_id]["player_order"][0]
                else:
                    games[room_id]["state"]["turn"] = None
            save_rooms()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
