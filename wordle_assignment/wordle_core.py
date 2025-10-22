"""
wordle_core.py
---------------------------------------------------
Core logic for Sandbox VR Wordle assignment.
Includes:
 - Normal Wordle game
 - Cheating Host (Absurdle-like)
 - Scoreboard persistence (Bonus)
---------------------------------------------------
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import random, json, os, time, threading

# Token symbols
HIT, PRESENT, MISS = "O", "?", "_"

def normalize(w: str) -> str:
    """Normalize input word: lowercase + trim."""
    return w.strip().lower()

def score_guess(answer: str, guess: str) -> List[str]:
    """
    Compute pattern between guess and answer.
    Returns list of 'O', '?', '_' representing:
      O = correct position (Hit)
      ? = letter present but wrong position
      _ = letter not present
    """
    a, g = normalize(answer), normalize(guess)
    if len(a) != len(g):
        raise ValueError("Guess length must match the answer length.")
    res, remain = [MISS] * len(a), {}

    # First pass: mark hits, record remaining letters
    for i in range(len(a)):
        if g[i] == a[i]:
            res[i] = HIT
        else:
            remain[a[i]] = remain.get(a[i], 0) + 1

    # Second pass: mark presents
    for i in range(len(a)):
        if res[i] == HIT:
            continue
        if remain.get(g[i], 0) > 0:
            res[i] = PRESENT
            remain[g[i]] -= 1

    return res


# ---------------- Game Config & Results ---------------- #

@dataclass
class GameConfig:
    """Game configuration: max rounds + word list."""
    max_rounds: int = 6
    word_list: List[str] = field(default_factory=list)

@dataclass
class RoundResult:
    """Single round result container."""
    guess: str
    tokens: List[str]
    remaining: int
    won: bool
    over: bool


# ---------------- Normal Wordle ---------------- #

class NormalWordleGame:
    """Standard Wordle implementation."""
    def __init__(self, answer: str, cfg: GameConfig):
        self.answer = normalize(answer)
        self.cfg = cfg
        self.round = 0
        self.history: List[RoundResult] = []

    def guess_word(self, word: str) -> RoundResult:
        """Handle a player's guess and return result."""
        word = normalize(word)
        if len(word) != len(self.answer):
            raise ValueError("Guess must be same length as answer.")
        if word not in self.cfg.word_list:
            raise ValueError("Word not found in dictionary.")

        self.round += 1
        tokens = score_guess(self.answer, word)
        won = all(t == HIT for t in tokens)
        over = won or self.round >= self.cfg.max_rounds
        rr = RoundResult(word, tokens, self.cfg.max_rounds - self.round, won, over)
        self.history.append(rr)

        print(f"[DEBUG] Round {self.round}: {word.upper()} -> {''.join(tokens)} "
              f"(remaining={rr.remaining}, won={rr.won}, over={rr.over})")

        return rr


# ---------------- Cheating Host Wordle ---------------- #

class CheatingWordleGame:
    """
    Absurdle-like implementation:
    The host changes its candidate list dynamically to prolong the game.
    It always chooses the candidate bucket with:
      1. fewest Hits,
      2. fewest Presents,
      3. largest number of candidates (tie-breaker).
    """
    def __init__(self, cfg: GameConfig):
        self.cfg = cfg
        self.candidates = set(cfg.word_list)
        self.final = None
        self.round = 0

    def guess_word(self, word: str) -> RoundResult:
        """Simulate cheating host's response."""
        word = normalize(word)
        if word not in self.cfg.word_list:
            raise ValueError("Word not found in dictionary.")
        if self.final:
            # Once final word fixed, behave like normal game
            return NormalWordleGame(self.final, self.cfg).guess_word(word)

        self.round += 1
        buckets: Dict[Tuple[int, int, Tuple[str, ...]], set] = {}

        # Partition candidates by pattern
        for c in self.candidates:
            pat = tuple(score_guess(c, word))
            h = sum(t == HIT for t in pat)
            p = sum(t == PRESENT for t in pat)
            buckets.setdefault((h, p, pat), set()).add(c)

        # Select best bucket (least hits, least presents, then largest)
        best_key = None
        best_set = set()
        for k, s in buckets.items():
            if not best_key:
                best_key, best_set = k, s
                continue
            h, p, _ = k
            bh, bp, _ = best_key
            if (h, p) < (bh, bp) or ((h, p) == (bh, bp) and len(s) > len(best_set)):
                best_key, best_set = k, s

        self.candidates = best_set
        tokens = list(best_key[2])
        if len(self.candidates) == 1:
            self.final = next(iter(self.candidates))

        over = self.round >= self.cfg.max_rounds
        rr = RoundResult(word, tokens, self.cfg.max_rounds - self.round, False, over)

        print(f"[DEBUG] Cheat Round {self.round}: {word.upper()} -> {''.join(tokens)} "
              f"(remaining={rr.remaining}, candidates={len(self.candidates)})")

        return rr


# ---------------- Bonus: Scoreboard ---------------- #

score_file = "data/scoreboard.json"
lock = threading.Lock()

def record_score(player: str, rounds: int, win: bool):
    """
    Append a record to scoreboard.
    Each entry: {player, rounds, win, timestamp}.
    """
    os.makedirs("data", exist_ok=True)
    with lock:
        data = []
        if os.path.exists(score_file):
            with open(score_file) as f:
                data = json.load(f)
        data.append({
            "player": player,
            "rounds": rounds,
            "win": win,
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        with open(score_file, "w") as f:
            json.dump(data, f, indent=2)

    print(f"[INFO] Score recorded for {player} → "
          f"{'WIN' if win else 'LOSE'} in {rounds} rounds.")
    print(f"[INFO] Scoreboard file: {os.path.abspath(score_file)}")
