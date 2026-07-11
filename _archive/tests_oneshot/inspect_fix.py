"""Inspecte et corrige test_cli_hdrctl.py."""
from pathlib import Path

TARGET = Path(__file__).parent / "test_cli_hdrctl.py"
content = TARGET.read_bytes()

# Chercher les problèmes
for term in [b'invalide', b'\\!', b'result ']:
    idx = content.rfind(term)
    if idx != -1:
        print(f"{term}: pos {idx} -> {repr(content[idx:idx+60])}")

# Trouver la troncature - chercher la dernière ligne complète
lines = content.split(b'\n')
print(f"\nTotal lines: {len(lines)}")
print(f"Last 3 lines: {[repr(l) for l in lines[-3:]]}")
