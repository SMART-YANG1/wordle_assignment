# Wordle Assignment — Multiplayer Server

This repository implements a Wordle-like game with:

- **Single-player (normal/cheat)**
- **Multiplayer rooms** with server-authoritative logic
- A **threaded CLI client** that receives events continuously

> Server: `server.py` 
> Client: `client.py` (threaded receiver model)  
> Core: `wordle_core.py` (scoring, core game classes)

---

## 1. Features Overview

### ✅ Server-Authoritative Design

- The **server** holds the single source of truth (answer, round counters, history).
- **Clients do not compute** scores; they render responses/broadcasts.

### ✅ Modes

- **Single-player normal** — fixed answer; 6 attempts.
- **Single-player cheat** — “host cheating” (Absurdle-like) to make it hard to win.
- **Multiplayer room** — multiple players share the same game state & answer and receive synchronized updates.

### ✅ Protocol (TCP + JSON)

- Simple newline-delimited JSON over TCP (`socketserver`).
- Actions: `create`, `create_multi`, `join`, `guess`.

### ✅ Concurrency Correctness

- **Per-room lock** guarantees atomic updates to game state.
- **Deterministic I/O order** in multiplayer guesses: **ACK to the sender first**, then **broadcast** to all.
- **No duplicate `join` broadcasts** — `join` only broadcasts once, during `join` action.

### ✅ First-Guess UX

- The sender always sees an immediate `✅ Response OK` on the very first guess (and every guess).
- Any prior `join` broadcasts are handled by the threaded client in background, so they never “spill” into the next command.

---

## 2. Repository Layout

```
.
├─ server.py          # authoritative server (matches this README)
├─ client.py          # threaded client that continuously receives & prints messages
├─ wordle_core.py     # scoring, classes: NormalWordleGame, CheatingWordleGame, etc.
└─ wordlists/
   └── common_5.txt    # UTF-8; one 5-letter word per line; alphabetic only
```

> Make sure `wordlists/common_5.txt` contains only **5-letter alphabetic** words.  
> The server validates this on startup and ignores invalid entries.

---

## 3. Installation & Requirements

- **Python:** 3.9+ recommended
- **OS:** macOS / Linux / Windows
- **Dependencies:** Only standard library (`socketserver`, `json`, `threading`, etc.)

No third-party packages are required.

---

## 4. How to Run

### 4.1 Start the Server

```bash
python3 server.py
```

Expected startup logs:

```
[INFO] Loaded N valid words from wordlists/common_5.txt
[START] Wordle Server running at 127.0.0.1:5050
[INFO] Actions: create, create_multi, join, guess
----------------------------------------------
```

> If you encounter **Address already in use**, kill the old process (macOS example):
>
> ```bash
> lsof -i :5050
> kill -9 <PID>
> ```

### 4.2 Start Clients (in two terminals)

Terminal A (Alice):

```bash
python3 client.py --name alice
```

Terminal B (Bob):

```bash
python3 client.py --name bob
```

**The client is threaded**: it spawns a background receiver that continuously prints any server messages the moment they arrive. This ensures no “old join events” are delayed until the next command.

---

## 5. JSON Protocol (Detailed)

All requests and responses are newline-delimited JSON objects. Below are supported actions and schemas.

### 5.1 `create` (single-player)

**Request:**

```json
{"action":"create","mode":"normal"}
```

- `mode`: `"normal"` or `"cheat"`

**Response:**

```json
{"ok": true, "game_id": "1234"}
```

Use this `game_id` with `guess` for single-player.

### 5.2 `create_multi` (multiplayer)

**Request:**

```json
{"action":"create_multi"}
```

**Response:**

```json
{"ok": true, "game_id": "5678"}
```

This creates a room that multiple clients can `join`.

### 5.3 `join` (multiplayer)

**Request:**

```json
{"action":"join","game_id":"5678","player":"alice"}
```

**Response (ACK to the joining client):**

```json
{"ok": true, "joined":"alice", "players":["alice"]}
```

**Broadcast (to all in the room, including the joiner):**

```json
{"event":"join","data":{"player":"alice","players":["alice"]}}
```

> The server only broadcasts **join** during the `join` action. It never re-broadcasts join during `guess`.

### 5.4 `guess` (single-player or multiplayer)

**Request:**

```json
{"action":"guess","game_id":"5678","player":"alice","word":"apple"}
```

**Deterministic I/O order:**

1) **ACK to the sender (always)**:

```json
{
  "ok": true,
  "player": "alice",
  "tokens": ["_","?","O","_","_"],
  "won": false,
  "over": false,
  "remaining": 5
}
```

2) **Broadcast to all players (including the sender)**:

```json
{
  "event": "guess",
  "data": {
    "player": "alice",
    "tokens": ["_","?","O","_","_"],
    "won": false,
    "over": false,
    "remaining": 5
  }
}
```

**Game over event (if the guess wins):**

```json
{"event":"game_over","winner":"alice"}
```

**Error cases (uniform):**

```json
{"ok": false, "error": "Guess length must match the answer length."}
```

- Illegal guesses (wrong length / non-alphabetic / not in dictionary where enforced) **do not** advance rounds and are **not** broadcast.

---

## 6. Scoring Semantics

From `wordle_core.py`:

- `O` — correct letter in the correct position (hit)
- `?` — correct letter in the wrong position (present)
- `_` — letter not in the answer (miss)

`score_guess(answer, guess)` computes the per-position feedback respecting per-letter counts and positions.

---

## 7. Client Usage Examples (Step-by-Step)

**Alice terminal:**

```text
>> {"action":"create_multi"}
# ACK: {"ok": true, "game_id": "7812"}

>> {"action":"join","game_id":"7812","player":"alice"}
# ACK: {"ok": true, "joined": "alice", "players": ["alice"]}
# EVENT (also printed): {"event":"join","data":{"player":"alice","players":["alice"]}}

>> {"action":"guess","game_id":"7812","player":"alice","word":"apple"}
# ACK:   {"ok": true, "player":"alice","tokens":["_","?","_","_","_"],"remaining":5,...}
# EVENT: {"event":"guess","data":{... the same data ...}}
```

**Bob terminal:**

```text
>> {"action":"join","game_id":"7812","player":"bob"}
# ACK: {"ok": true, "joined":"bob", "players":["alice","bob"]}
# EVENT (to both): {"event":"join","data":{"player":"bob","players":["alice","bob"]}}

# When Alice guesses, Bob immediately sees the broadcast:
# EVENT: {"event":"guess","data":{...}}
```

**If someone wins:**
Both terminals receive:

```json
{"event":"game_over","winner":"alice"}
```

---

## 8. Design Guarantees (Invariants)

- **I1**: Every request gets an ACK (either `ok:true` or `ok:false`), even on error.
- **I2**: Only legal guesses advance the round; illegal inputs return error and do not broadcast.
- **I3**: Within the same round, `tokens/won/over/remaining` seen by all clients are the same (server snapshot).
- **I4**: `join` is only broadcast during `join` action; never during `guess`.
- **I5**: `game_over` is emitted once; further guesses are rejected with `ok:false`.

Per-room locking ensures atomic updates and eliminates race conditions in multiplayer.

---

## 9. Troubleshooting

### “First guess shows old join events before guess”

Use the **threaded client** (`client.py` in this repo). It continuously reads & prints messages in the background so previous events never accumulate and “spill” into the next command.

### “Address already in use”

Kill the previous process holding port 5050:

```bash
lsof -i :5050
kill -9 <PID>
```

### “Guess length must match the answer length.”

Ensure you’re sending a **5-letter alphabetic** word. Also verify your dictionary file `wordlists/common_5.txt` has only 5-letter words (UTF-8, one per line).

### “Game already over.”

Once someone wins in a room, subsequent guesses are rejected. Create a new room with `create_multi` to continue.

---

## 10. Security & Integrity Notes

- The server is authoritative and is the only component producing `tokens/won/over/remaining`.
- Clients are untrusted: they only display server responses/broadcasts.
- Illegal input never mutates game state and produces an immediate error response.

---

## 11. Extending the System (Optional Ideas)

- Add **room TTL** and cleanup for inactive rooms.
- Add **spectator** role (read-only stream).
- Add **per-room scoreboard** or **leaderboard** persistent storage.
- WebSocket / HTTP gateway for browser clients.

---

## 12. License

This assignment repository is intended for interview/demo purposes.  
Feel free to adapt the code for your submission.

---

## 13. Quick Checklist (Before You Demo)

- [ ] `python3 server.py` runs without errors  
- [ ] `client.py --name alice` + `client.py --name bob` both connect  
- [ ] `create_multi` → `join` (both) → `guess` (Alice) → both terminals see synchronized messages  
- [ ] Winning guess emits exactly one `game_over`
