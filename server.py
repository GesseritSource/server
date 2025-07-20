from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

app = FastAPI()

# Allow CORS for local and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (for demo/small scale)
games = {}
connections = {}

class PlayerAction(BaseModel):
    player: str
    action: dict

def next_player(players, current):
    idx = players.index(current)
    return players[(idx + 1) % len(players)]

@app.post("/create_room")
def create_room():
    room_id = str(uuid.uuid4())[:8]
    games[room_id] = {
        "players": [],
        "state": {
            "turn": None,
            "actions": [],
            "grid": [[None for _ in range(6)] for _ in range(6)],
            "player_positions": {},
            "player_hp": {},
        }
    }
    connections[room_id] = []
    return {"room_id": room_id}

@app.post("/join_room/{room_id}")
def join_room(room_id: str, player: str):
    if room_id not in games:
        return {"error": "Room not found"}
    if player not in games[room_id]["players"]:
        games[room_id]["players"].append(player)
        games[room_id]["state"]["player_positions"][player] = (5, len(games[room_id]["players"]))
        games[room_id]["state"]["player_hp"][player] = 10
    if games[room_id]["state"]["turn"] is None:
        games[room_id]["state"]["turn"] = games[room_id]["players"][0]
    return {"ok": True, "players": games[room_id]["players"]}

@app.websocket("/ws/{room_id}/{player}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player: str):
    await websocket.accept()
    if room_id not in connections:
        connections[room_id] = []
    connections[room_id].append(websocket)
    try:
        # Send initial state
        await websocket.send_json(games[room_id]["state"])
        while True:
            data = await websocket.receive_json()
            # Only accept actions from the player whose turn it is
            if data.get("type") == "action":
                if games[room_id]["state"]["turn"] != player:
                    await websocket.send_json({"error": "Not your turn"})
                    continue
                # Apply action (expand this logic for your game)
                action = data["action"]
                games[room_id]["state"]["actions"].append({"player": player, "action": action})
                # Example: move
                if "move" in action:
                    pos = games[room_id]["state"]["player_positions"][player]
                    if action["move"] == "up":
                        games[room_id]["state"]["player_positions"][player] = (max(0, pos[0] - 1), pos[1])
                    elif action["move"] == "down":
                        games[room_id]["state"]["player_positions"][player] = (min(5, pos[0] + 1), pos[1])
                    elif action["move"] == "left":
                        games[room_id]["state"]["player_positions"][player] = (pos[0], max(0, pos[1] - 1))
                    elif action["move"] == "right":
                        games[room_id]["state"]["player_positions"][player] = (pos[0], min(5, pos[1] + 1))
                    # Add more movement/attack logic here
                # Advance turn
                games[room_id]["state"]["turn"] = next_player(games[room_id]["players"], player)
                # Broadcast new state to all
                for conn in connections[room_id]:
                    await conn.send_json(games[room_id]["state"])
    except WebSocketDisconnect:
        connections[room_id].remove(websocket)
