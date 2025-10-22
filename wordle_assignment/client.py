import socket
import json
import threading
import sys
import argparse

PRINT_LOCK = threading.Lock()

def pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)

def print_safe(prefix, obj=None):
    with PRINT_LOCK:
        if obj is None:
            print(prefix)
        else:
            print(prefix)
            print(pretty(obj))
        sys.stdout.flush()

def recv_loop(sock: socket.socket, player_name: str):
    """
    Background receiver: continuously read and print ANY server message
    as soon as it arrives, so nothing stays queued until the next send.
    """
    f = sock.makefile("r", encoding="utf-8", newline="\n")
    while True:
        line = f.readline()
        if not line:
            print_safe("⚠️  Server closed the connection.")
            break
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            print_safe("⚠️  Non-JSON message:", line)
            continue

        # Classify and print
        if "event" in obj:
            evt = obj["event"]
            print_safe(f"\n📡 Event: {evt}", obj)
        elif "ok" in obj:
            if obj["ok"]:
                print_safe("\n✅ Response OK:", obj)
            else:
                print_safe("\n❌ Error:", obj)
        else:
            print_safe("\n⚠️  Unknown message:", obj)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--name", default="anon", help="player name for convenience")
    args = ap.parse_args()

    print_safe(f"🌐 Connecting to Wordle server at {args.host}:{args.port} ...")
    s = socket.create_connection((args.host, args.port))
    print_safe("✅ Connected!")

    # Start background receiver thread
    t = threading.Thread(target=recv_loop, args=(s, args.name), daemon=True)
    t.start()

    print_safe(
        "📖 Examples:\n"
        "  {\"action\":\"create_multi\"}\n"
        f"  {{\"action\":\"join\",\"game_id\":\"1234\",\"player\":\"{args.name}\"}}\n"
        f"  {{\"action\":\"guess\",\"game_id\":\"1234\",\"player\":\"{args.name}\",\"word\":\"apple\"}}\n"
        "Ctrl+C / Ctrl+D to exit.\n"
    )

    try:
        while True:
            try:
                line = input(">> ").strip()
            except EOFError:
                break
            if not line:
                continue
            # Send raw line + newline
            s.sendall((line + "\n").encode("utf-8"))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        s.close()
        print_safe("\n🔒 Connection closed.")

if __name__ == "__main__":
    main()
