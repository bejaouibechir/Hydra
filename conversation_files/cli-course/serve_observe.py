import sys

sys.path.insert(0, r"C:\Users\DELL\Desktop\Hydra")
sys.argv = [
    "hdrctl",
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    "5689",
    "--workspace",
    r"C:\Users\DELL\Desktop\Hydra\conversation_files\cli-course",
]

from cli.hdrctl import main

main()
