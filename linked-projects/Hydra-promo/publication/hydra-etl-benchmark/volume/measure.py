"""Lance une commande, mesure durée et mémoire maximale (somme RSS de l'arbre de processus)."""
import json, subprocess, sys, time
import psutil
cmd, cwd, timeout = sys.argv[1], sys.argv[2], float(sys.argv[3])
t0 = time.monotonic()
p = subprocess.Popen(["bash", "-c", cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
peak, proc = 0, psutil.Process(p.pid)
out_lines = []
import threading
def reader():
    for ln in p.stdout:
        out_lines.append(ln)
th = threading.Thread(target=reader, daemon=True); th.start()
killed = False
while p.poll() is None:
    try:
        rss = proc.memory_info().rss + sum(c.memory_info().rss for c in proc.children(recursive=True))
        peak = max(peak, rss)
    except psutil.Error:
        pass
    if time.monotonic() - t0 > timeout:
        for c in proc.children(recursive=True):
            c.kill()
        p.kill(); killed = True
    time.sleep(0.2)
th.join(2)
print(json.dumps({"seconds": round(time.monotonic() - t0, 2), "peak_mb": round(peak / 1e6), "exit": p.returncode,
                  "timeout": killed, "tail": "".join(out_lines[-6:])[-600:]}))
