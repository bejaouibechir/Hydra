"""Corrige la corruption \!= dans test_cli_hdrctl.py."""
from pathlib import Path

TARGET = Path(__file__).parent / "test_cli_hdrctl.py"
content = TARGET.read_bytes()

# Trouver et supprimer la partie corrompue (tout ce qui vient après le premier \!)
# Le fichier original se termine à la position du \!
corrupt_idx = content.find(b'\\!')
if corrupt_idx == -1:
    print("Pas de corruption trouvée")
else:
    # Remonter jusqu'au début de la ligne corrompue
    line_start = content.rfind(b'\n', 0, corrupt_idx) + 1
    print(f"Corruption at {corrupt_idx}, line starts at {line_start}")
    print(f"Corrupt line: {repr(content[line_start:line_start+80])}")

    # Garder tout jusqu'avant cette ligne (c'est la fin tronquée originale)
    clean = content[:line_start]

    # Ajouter la fin correcte
    suffix = (
        b'        result = runner.invoke(cli, ["run", str(job), "-v"])\r\n'
        b'        assert result.exit_code == 0\r\n'
        b'\r\n'
        b'\r\n'
        b'class TestErrors:\r\n'
        b'\r\n'
        b'    def test_run_missing_dir(self, runner):\r\n'
        b'        result = runner.invoke(cli, ["run", "/nonexistent/path"])\r\n'
        b'        assert result.exit_code != 0\r\n'
        b'\r\n'
        b'    def test_validate_missing_dir(self, runner):\r\n'
        b'        result = runner.invoke(cli, ["validate", "/nonexistent/path"])\r\n'
        b'        assert result.exit_code != 0\r\n'
        b'\r\n'
        b'    def test_list_missing_dir(self, runner):\r\n'
        b'        result = runner.invoke(cli, ["list", "/nonexistent/path"])\r\n'
        b'        assert result.exit_code != 0\r\n'
    )

    fixed = clean + suffix
    TARGET.write_bytes(fixed)
    print(f"Fixed, size: {len(fixed)}")

    import py_compile
    try:
        py_compile.compile(str(TARGET), doraise=True)
        print("Syntax OK")
    except py_compile.PyCompileError as e:
        print(f"Syntax error: {e}")
