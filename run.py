"""
Annam Loop Runner Script
Starts both the Flask Web App (port 5000) and the MCP Server (port 8000) concurrently.

Instructions to run them separately:
  1. Start the MCP Server:
       python mcp_server.py
  2. Start the Flask App:
       python app.py
"""

import sys
import time
import subprocess
import signal
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    print("=" * 65)
    print("  ANNAM LOOP - FOOD RESCUE & REDISTRIBUTION")
    print("=" * 65)
    print("Starting background services:")
    print("  * MCP Server: http://127.0.0.1:8000/mcp (Streamable HTTP)")
    print("  * Flask App:  http://127.0.0.1:5000     (Web & Voice UI)")
    print("=" * 65)
    print("Tip: To run services separately in different terminals:")
    print("  Terminal 1: python mcp_server.py")
    print("  Terminal 2: python app.py")
    print("=" * 65)

    python_executable = sys.executable

    # Start MCP server subprocess
    mcp_proc = subprocess.Popen(
        [python_executable, "mcp_server.py"],
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    # Allow MCP server 1.5s to bind to port 8000
    time.sleep(1.5)

    # Start Flask app subprocess
    flask_proc = subprocess.Popen(
        [python_executable, "app.py"],
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    print("\n[OK] Both services are now running!")
    print("Press Ctrl+C to terminate both services cleanly.\n")

    def signal_handler(sig, frame):
        print("\nShutting down Annam Loop services...")
        flask_proc.terminate()
        mcp_proc.terminate()
        flask_proc.wait()
        mcp_proc.wait()
        print("All processes stopped successfully. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal_handler)

    try:
        while True:
            if mcp_proc.poll() is not None:
                print("MCP Server terminated unexpectedly.")
                flask_proc.terminate()
                break
            if flask_proc.poll() is not None:
                print("Flask App terminated unexpectedly.")
                mcp_proc.terminate()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
