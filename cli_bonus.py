from wordle_core import GameConfig, NormalWordleGame, record_score
import random

def load_words(path):
    """Load 5-letter words from the given wordlist file."""
    with open(path) as f:
        return [x.strip() for x in f if x.strip()]

def colorize(tokens, word):
    """
    Colorize the result of a guess:
    Green = correct position,
    Yellow = present but wrong position,
    Gray = not in word.
    """
    colors = {'O': '\033[92m', '?': '\033[93m', '_': '\033[90m'}
    return ''.join(f"{colors[t]}{ch.upper()}\033[0m" for ch, t in zip(word, tokens))

def main():
    # Load the word list and set up configuration
    wl = load_words('wordlists/common_5.txt')
    cfg = GameConfig(max_rounds=6, word_list=wl)
    answer = random.choice(wl)
    game = NormalWordleGame(answer, cfg)

    print('🎮 Wordle Bonus Mode – Colored CLI + Remaining Attempts')
    print(f"🔢 You have {cfg.max_rounds} chances to guess a 5-letter word!")
    player = input('Enter your name: ').strip() or 'anon'

    # Game loop
    while True:
        guess = input(f'Guess #{game.round + 1}: ').strip().lower()
        if not guess:
            continue
        try:
            rr = game.guess_word(guess)
        except Exception as e:
            print('⚠️ Error:', e)
            continue

        # Print colored feedback and remaining attempts
        print(colorize(rr.tokens, guess), f' (remaining attempts: {rr.remaining})')

        # Check if the player has won
        if rr.won:
            print(f'🏆 Congratulations {player}! You guessed it in {len(game.history)} rounds.')
            record_score(player, len(game.history), True)
            break

        # Check if game is over
        if rr.over:
            print(f'💀 Sorry, game over. The correct answer was: {answer.upper()}')
            record_score(player, len(game.history), False)
            break

    print('📊 Your result has been saved to the scoreboard (data/scoreboard.json).')

if __name__ == '__main__':
    main()
