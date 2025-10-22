import socketserver
import json
import random
from typing import Dict, Set
import threading
from wordle_core import GameConfig, NormalWordleGame, CheatingWordleGame

# ----------- Load valid words -----------
def load_words(path: str):
    """Load valid 5-letter alphabetic words from file (UTF-8)."""
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            w = line.strip().lower().replace("\ufeff", "")
            if w and len(w) == 5 and w.isalpha():
                words.append(w)
    print(f"[INFO] Loaded {len(words)} valid words from {path}")
    return words

WL = load_words("wordlists/common_5.txt")
CFG = GameConfig(6, WL)

# ----------- Global stores -----------
sessions: Dict[str, NormalWordleGame] = {}  # single-player sessions
multis: Dict[str, "MultiRoom"] = {}         # multiplayer rooms

# ----------- Multiplayer room -----------
class MultiRoom:
    """
    Authoritative multiplayer room state.
    Invariants:
      - A single NormalWordleGame instance holds the truth.
      - room.lock guards all state transitions in this room.
      - Streams are only mutated in 'join' (not in 'guess').
    """
    def __init__(self, answer: str):
        self.answer = answer
        self.game = NormalWordleGame(answer, CFG)
        self.players: Set[str] = set()
        self.streams: Set[socketserver.StreamRequestHandler] = set()
        self.over = False
        self.lock = threading.Lock()  # per-room lock

# ----------- Helpers -----------
def new_id() -> str:
    return str(random.randint(1000, 9999))

def send_json(handler: socketserver.StreamRequestHandler, obj: dict):
    """Send one JSON response to a single client (I1)."""
    try:
        handler.wfile.write((json.dumps(obj) + "\n").encode())
        handler.wfile.flush()
    except Exception as e:
        print(f"[WARN] Send failed: {e}")

def broadcast(room: MultiRoom, msg: dict):
    """Broadcast JSON to all clients in room.streams (remove dead)."""
    dead = []
    for h in list(room.streams):
        try:
            h.wfile.write((json.dumps(msg) + "\n").encode())
            h.wfile.flush()
        except Exception:
            dead.append(h)
    for d in dead:
        room.streams.discard(d)
    print(f"[BROADCAST] {msg.get('event','unknown')} -> {len(room.streams)} clients")

# ----------- Main handler -----------
class Handler(socketserver.StreamRequestHandler):
    """
    TCP JSON protocol:
      - create       (single-player normal/cheat)
      - create_multi (multiplayer room)
      - join         (enter a room)
      - guess        (try a word; server authoritative)
    """
    def handle(self):
        ip = self.client_address[0]
        print(f"[INFO] Connected from {ip}")

        while True:
            line = self.rfile.readline()
            if not line:
                print(f"[INFO] Client {ip} disconnected.")
                break

            try:
                req = json.loads(line.decode().strip())
                act = req.get("action")

                # -------- Single-player create --------
                if act == "create":
                    mode = req.get("mode", "normal")
                    gid = new_id()
                    if mode == "normal":
                        sessions[gid] = NormalWordleGame(random.choice(WL), CFG)
                    elif mode == "cheat":
                        sessions[gid] = CheatingWordleGame(CFG)
                    else:
                        raise ValueError("Unknown mode.")
                    send_json(self, {"ok": True, "game_id": gid})
                    continue

                # -------- Create multiplayer room --------
                if act == "create_multi":
                    gid = new_id()
                    ans = random.choice(WL)
                    multis[gid] = MultiRoom(ans)
                    print(f"[MULTI] Room {gid} created (answer={ans}).")
                    send_json(self, {"ok": True, "game_id": gid})
                    continue

                # -------- Join room --------
                if act == "join":
                    gid = req.get("game_id")
                    player = req.get("player", "anon")
                    room = multis.get(gid)
                    if not room:
                        raise ValueError(f"Room {gid} not found.")

                    # Only mutate membership under room lock
                    with room.lock:
                        room.players.add(player)
                        if self not in room.streams:
                            room.streams.add(self)

                        # Prepare snapshot for ack & broadcast
                        players_list = list(room.players)

                    # Ack to the joining client (I1)
                    send_json(self, {
                        "ok": True,
                        "joined": player,
                        "players": players_list
                    })

                    # Broadcast join once (I4)
                    broadcast(room, {
                        "event": "join",
                        "data": {"player": player, "players": players_list}
                    })
                    continue

                # -------- Guess (single/multi) --------
                if act == "guess":
                    gid = req.get("game_id")
                    word = req.get("word", "").lower()
                    player = req.get("player", "anon")

                    # ---- Multiplayer branch ----
                    if gid in multis:
                        room = multis[gid]

                        # All room state transitions under lock (I2, I3, I5)
                        with room.lock:
                            if self not in room.streams:
                                # late-join or reconnect: attach once; do not broadcast join here
                                room.streams.add(self)

                            if room.over:
                                # I5: after game over, reject further guesses
                                send_json(self, {"ok": False, "error": "Game already over."})
                                continue

                            # Try to apply the guess; invalid guesses must not advance rounds (I2)
                            try:
                                rr = room.game.guess_word(word)  # authoritative scoring
                            except Exception as e:
                                # Illegal guess: do not touch room.over; do not broadcast
                                send_json(self, {"ok": False, "error": str(e)})
                                continue

                            # Snapshot for consistency (I3)
                            data = {
                                "player": player,
                                "tokens": rr.tokens,
                                "won": rr.won,
                                "over": rr.over,
                                "remaining": rr.remaining  # from authoritative game
                            }

                            # Decide winner under the lock to avoid double-wins (I5)
                            winner = player if rr.won and not room.over else None
                            if winner:
                                room.over = True

                        # Lock released; now send messages in deterministic order (ack -> broadcast)
                        send_json(self, {"ok": True, **data})               # ack to sender (I1)
                        broadcast(room, {"event": "guess", "data": data})   # fan-out to all (I3)

                        if winner:
                            broadcast(room, {"event": "game_over", "winner": winner})
                        continue

                    # ---- Single-player branch ----
                    game = sessions.get(gid)
                    if not game:
                        raise ValueError(f"Unknown game ID {gid}")

                    try:
                        rr = game.guess_word(word)
                    except Exception as e:
                        send_json(self, {"ok": False, "error": str(e)})
                        continue

                    send_json(self, {
                        "ok": True,
                        "tokens": rr.tokens,
                        "won": rr.won,
                        "over": rr.over,
                        "remaining": rr.remaining
                    })
                    continue

                # -------- Unknown action --------
                raise ValueError(f"Unknown action: {act}")

            except Exception as e:
                print(f"[ERROR] {type(e).__name__}: {e}")
                send_json(self, {"ok": False, "error": str(e)})

# -------- Threaded TCP server --------
class S(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    host, port = "127.0.0.1", 5050
    print(f"[START] Wordle Server v3.0 running at {host}:{port}")
    print("[INFO] Actions: create, create_multi, join, guess")
    print("[INFO] -------------------------------------------")
    with S((host, port), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[STOP] Server stopped manually.")
