"""Empaqueta, firma y publica una versión de Centro de Mando.

Uso (desde la raíz del proyecto, con la versión ya compilada en build/CentroDeMando):

	python tools/publicar.py                    # crea dist/CentroDeMando_v<versión>.zip y dist/version.json firmado
	python tools/publicar.py --servidor         # además los copia a la carpeta del servidor (Synology Drive)
	python tools/publicar.py --servidor --github  # y crea la release v<versión> en GitHub con los dos archivos

Qué hace:

1. Comprueba que la compilación existe, es de esta versión y no lleva datos
   personales en data/ (configuración, registros, bases de datos...).
2. Crea el ZIP con todo dentro de la carpeta «CentroDeMando» (lo que espera el
   actualizador).
3. Escribe version.json (app, version, file, sha256, size, date, novedades) y lo
   firma con la clave privada de tools/claves (Ed25519). La firma se verifica.
4. Servidor: copia primero el ZIP y DESPUÉS version.json (al revés, durante unos
   segundos las instalaciones verían una versión cuyo ZIP aún no existe).
5. GitHub: ``gh release create v<versión>`` con el ZIP y version.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

NOMBRE = "CentroDeMando"
BUILD = RAIZ / "build" / NOMBRE
DIST = RAIZ / "dist"
CARPETA_SERVIDOR = Path(r"C:\Users\xebol\SynologyDrive\web") / NOMBRE
REPOSITORIO = "hxebolax/CentroDeMando"
# Lo que nunca debe viajar en el paquete: datos de la persona que compiló.
PROHIBIDO_EN_DATA = {"config", "logs", "db", "cache", "temp", "sessions", "backups"}


def version_actual() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	return re.search(r'APP_VERSION\s*=\s*"([^"]+)"', texto).group(1)


def novedades_de(version: str) -> str:
	"""El apartado «## <versión>» de data/docs/novedades.md, en texto plano."""
	texto = (RAIZ / "data" / "docs" / "novedades.md").read_text(encoding="utf-8")
	partes = re.split(r"^## ", texto, flags=re.M)
	for parte in partes[1:]:
		cabecera, _, cuerpo = parte.partition("\n")
		if cabecera.strip().split()[0] == version:
			return re.sub(r"\*\*(.+?)\*\*", r"\1", cuerpo).strip()
	return ""


def comprobar_build(version: str) -> None:
	if not (BUILD / f"{NOMBRE}.exe").is_file():
		raise SystemExit(f"No existe {BUILD / (NOMBRE + '.exe')}: compile primero (entorno.bat compilar).")
	personales = sorted(p.name for p in (BUILD / "data").iterdir() if p.is_dir() and p.name in PROHIBIDO_EN_DATA)
	if personales:
		raise SystemExit(f"La compilación lleva datos personales en data: {', '.join(personales)}. Recompile desde cero.")
	# cx_Freeze copia el python3t.dll que reenvía al intérprete sin GIL; así
	# cryptography no carga y las instalaciones no pueden verificar firmas.
	for dll in (BUILD / "python3t.dll", BUILD / "lib" / "python3t.dll"):
		if dll.is_file() and re.search(rb"python3\d+t\.Py", dll.read_bytes()):
			raise SystemExit(f"{dll} reenvía al Python sin GIL: cryptography no cargará. Compile con setup_cx.py (lo corrige).")
	versiones = list((BUILD / "lib").rglob("version.py"))
	if not any(f'"{version}"' in v.read_text(encoding="utf-8", errors="ignore") for v in versiones if "core" in v.parts):
		print("Aviso: no se pudo confirmar la versión dentro de la compilación (puede estar en library.zip).")


def crear_zip(version: str) -> Path:
	DIST.mkdir(exist_ok=True)
	destino = DIST / f"{NOMBRE}_v{version}.zip"
	destino.unlink(missing_ok=True)
	with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as paquete:
		for archivo in sorted(BUILD.rglob("*")):
			if archivo.is_file() and "__pycache__" not in archivo.parts:
				paquete.write(archivo, Path(NOMBRE) / archivo.relative_to(BUILD))
	return destino


def crear_manifiesto(version: str, zip_: Path) -> Path:
	sha = hashlib.sha256()
	with open(zip_, "rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			sha.update(bloque)
	manifiesto = {
		"app": NOMBRE,
		"version": version,
		"file": zip_.name,
		"sha256": sha.hexdigest(),
		"size": zip_.stat().st_size,
		"date": time.strftime("%Y-%m-%d"),
		"novedades": novedades_de(version),
	}
	ruta = DIST / "version.json"
	ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
	return ruta


def firmar(ruta_json: Path) -> None:
	import importlib.util

	especificacion = importlib.util.spec_from_file_location("firmar_version", RAIZ / "tools" / "firmar_version.py")
	modulo = importlib.util.module_from_spec(especificacion)
	especificacion.loader.exec_module(modulo)
	clave = RAIZ / "tools" / "claves" / "firma_ed25519.key"
	if not clave.is_file():
		raise SystemExit("No está la clave privada en tools/claves: sin ella no se puede publicar una versión que acepten las instalaciones.")
	modulo.firmar(clave, ruta_json)
	from app.services import actualizador

	actualizador.verificar_firma(json.loads(ruta_json.read_text(encoding="utf-8")), actualizador.CLAVES_PUBLICAS_ED25519)
	print("Firma verificada con la clave pública del programa.")


def publicar_servidor(zip_: Path, manifiesto: Path) -> None:
	CARPETA_SERVIDOR.mkdir(parents=True, exist_ok=True)
	shutil.copy2(zip_, CARPETA_SERVIDOR / zip_.name)
	shutil.copy2(manifiesto, CARPETA_SERVIDOR / "version.json")
	print(f"Copiado al servidor: {CARPETA_SERVIDOR}")


def publicar_github(version: str, zip_: Path, manifiesto: Path) -> None:
	notas = DIST / "notas.md"
	notas.write_text(f"# Centro de Mando {version}\n\n{novedades_de(version)}\n", encoding="utf-8")
	subprocess.run(
		["gh", "release", "create", f"v{version}", str(zip_), str(manifiesto), "--repo", REPOSITORIO, "--title", f"Centro de Mando {version}", "--notes-file", str(notas)],
		check=True,
	)
	print(f"Release v{version} creada en https://github.com/{REPOSITORIO}/releases")


def main() -> int:
	analizador = argparse.ArgumentParser(description="Empaqueta, firma y publica Centro de Mando.")
	analizador.add_argument("--servidor", action="store_true", help="copiar a la carpeta del servidor (Synology Drive)")
	analizador.add_argument("--github", action="store_true", help="crear la release en GitHub")
	opciones = analizador.parse_args()
	version = version_actual()
	comprobar_build(version)
	zip_ = crear_zip(version)
	manifiesto = crear_manifiesto(version, zip_)
	firmar(manifiesto)
	print(f"{zip_.name}: {zip_.stat().st_size / 1048576:.1f} MB")
	if opciones.servidor:
		publicar_servidor(zip_, manifiesto)
	if opciones.github:
		publicar_github(version, zip_, manifiesto)
	return 0


if __name__ == "__main__":
	sys.exit(main())
