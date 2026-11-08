#!/usr/bin/env python3
"""
Pipeline de Build e Compressão Gzip dos Assets do Dashboard Vue.js 3 para o LittleFS
Copia e comprime os arquivos de frontend/dist/ para data/www/
"""

import os
import gzip
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
TARGET_WWW_DIR = ROOT_DIR / "data" / "www"

def run_build():
    print("[1/3] Executando 'npm run build' no frontend Vue.js 3...")
    res = subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print("Erro durante o build:")
        print(res.stderr)
        raise SystemExit(res.returncode)
    print("Build concluído com sucesso!")

def compress_and_export():
    print(f"[2/3] Comprimindo arquivos de {DIST_DIR} para {TARGET_WWW_DIR}...")
    
    if TARGET_WWW_DIR.exists():
        shutil.rmtree(TARGET_WWW_DIR)
    TARGET_WWW_DIR.mkdir(parents=True, exist_ok=True)

    total_orig = 0
    total_gz = 0

    for root, _, files in os.walk(DIST_DIR):
        for fname in files:
            src_file = Path(root) / fname
            rel_path = src_file.relative_to(DIST_DIR)
            dst_gz_file = TARGET_WWW_DIR / f"{rel_path}.gz"
            dst_gz_file.parent.mkdir(parents=True, exist_ok=True)

            with open(src_file, "rb") as f_in:
                data = f_in.read()
                orig_size = len(data)
                total_orig += orig_size

            with gzip.open(dst_gz_file, "wb", compresslevel=9) as f_out:
                f_out.write(data)

            gz_size = os.path.getsize(dst_gz_file)
            total_gz += gz_size

            # Também salva o arquivo descompactado como fallback se necessário
            dst_raw_file = TARGET_WWW_DIR / rel_path
            shutil.copy2(src_file, dst_raw_file)

            ratio = (1 - gz_size / orig_size) * 100
            print(f"  -> {rel_path}: {orig_size / 1024:.1f} KB -> {gz_size / 1024:.1f} KB.gz (-{ratio:.1f}%)")

    print(f"\n[3/3] Consolidação:")
    print(f"  Tamanho Original Total : {total_orig / 1024:.1f} KB")
    print(f"  Tamanho Gzip Final     : {total_gz / 1024:.1f} KB")
    print(f"  Economia de Banda/Flash: {(1 - total_gz / total_orig) * 100:.1f}%\n")
    print(f"Assets prontos em {TARGET_WWW_DIR} para serem gravados na partição LittleFS via 'pio run -t uploadfs'!")

if __name__ == "__main__":
    run_build()
    compress_and_export()
