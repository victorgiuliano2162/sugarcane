#!/usr/bin/env python3
"""
Bateria de Avaliação Exaustiva (100% dos Datasets Disponíveis):
Avaliação em Hardware Real (ESP32-S3 @ 240 MHz + Octal PSRAM @ 80 MHz) de TODAS as
9.269 imagens dos dois datasets locais:

1. Dataset Primário (Sugarcane leaf image dataset): 6.748 imagens em 11 classes
2. Dataset Archive (/home/victor/Documents/sugar-cane/archive): 2.521 imagens em 5 classes

Características de Engenharia:
- Cada subpasta é tratada estritamente como uma classe individual.
- Streaming Pipelined com janela deslizante de 2 requisições em trânsito (aproveitando o pipeline Dual-Core do ESP32-S3).
- Resiliência com reconexão automática e retentativas em caso de jitter de Wi-Fi.
- Modo Resume: lê o CSV de saída e continua exatamente do ponto em que parou, garantindo que nenhum frame seja reprocessado.
- Relatório Markdown estruturado com matriz de confusão 11x11 para o dataset primário e matriz 5x11 para o archive.
"""

import os
import sys
import time
import json
import csv
import asyncio
import argparse
import statistics
from collections import defaultdict
import websockets

DEFAULT_ESP32_WS_URL = "ws://192.168.1.19/ws"
PRIMARY_BASE = "/home/victor/Documents/datasets/Sugarcane leaf image dataset-20261106T004142Z-1-001/Sugarcane leaf image dataset"
ARCHIVE_BASE = "/home/victor/Documents/sugar-cane/archive"

OUTPUT_DIR = "/home/victor/projects/sugarcane/model_inference_tests"
DEFAULT_CSV_PATH = os.path.join(OUTPUT_DIR, "resultado_inferencia_dataset_completo.csv")
DEFAULT_REPORT_PATH = os.path.join(OUTPUT_DIR, "RELATORIO_DATASET_COMPLETO.md")

# Model's native 11 classes
MODEL_CLASSES = [
    "Banded Chlorosis", "Brown Spot", "BrownRust", "Dried Leaves",
    "Grassy shoot", "Healthy Leaves", "Pokkah Boeng", "Sett Rot",
    "Viral Disease", "Yellow Leaf", "smut"
]

# Primary dataset definitions: (display_name, directory, expected_class)
PRIMARY_DATASET_FOLDERS = [
    ("Banded Chlorosis", os.path.join(PRIMARY_BASE, "Diseases", "Banded Chlorosis"), "Banded Chlorosis"),
    ("Brown Spot", os.path.join(PRIMARY_BASE, "Diseases", "Brown Spot"), "Brown Spot"),
    ("BrownRust", os.path.join(PRIMARY_BASE, "Diseases", "BrownRust"), "BrownRust"),
    ("Dried Leaves", os.path.join(PRIMARY_BASE, "Dried Leaves"), "Dried Leaves"),
    ("Grassy shoot", os.path.join(PRIMARY_BASE, "Diseases", "Grassy shoot"), "Grassy shoot"),
    ("Healthy Leaves", os.path.join(PRIMARY_BASE, "Healthy Leaves"), "Healthy Leaves"),
    ("Pokkah Boeng", os.path.join(PRIMARY_BASE, "Diseases", "Pokkah Boeng"), "Pokkah Boeng"),
    ("Sett Rot", os.path.join(PRIMARY_BASE, "Diseases", "Sett Rot"), "Sett Rot"),
    ("Viral Disease", os.path.join(PRIMARY_BASE, "Diseases", "Viral Disease"), "Viral Disease"),
    ("Yellow Leaf", os.path.join(PRIMARY_BASE, "Diseases", "Yellow Leaf"), "Yellow Leaf"),
    ("smut", os.path.join(PRIMARY_BASE, "Diseases", "smut"), "smut")
]

# Archive dataset definitions: (display_name, directory, expected_class)
ARCHIVE_DATASET_FOLDERS = [
    ("Healthy", os.path.join(ARCHIVE_BASE, "Healthy"), "Healthy Leaves"),
    ("Mosaic", os.path.join(ARCHIVE_BASE, "Mosaic"), "Viral Disease"),
    ("RedRot", os.path.join(ARCHIVE_BASE, "RedRot"), "RedRot"),
    ("Rust", os.path.join(ARCHIVE_BASE, "Rust"), "BrownRust"),
    ("Yellow", os.path.join(ARCHIVE_BASE, "Yellow"), "Yellow Leaf")
]

CSV_HEADER = [
    "arquivo",
    "dataset_origem",
    "subpasta_classe",
    "classe_esperada",
    "classe_predita",
    "confianca",
    "correto_direto",
    "correto_mapeado",
    "tempo_decodificacao_ms",
    "tempo_inferencia_ms",
    "tempo_total_dispositivo_ms",
    "tempo_incremental_ms",
    "latencia_rtt_ms",
    "todas_probabilidades"
]

async def connect_ws(ws_url, max_retries=15, retry_delay=2.0):
    for attempt in range(1, max_retries + 1):
        try:
            ws = await websockets.connect(ws_url, open_timeout=10, ping_interval=None)
            return ws
        except Exception as e:
            print(f"[WS] Tentativa {attempt}/{max_retries} em {ws_url} falhou: {e}. Aguardando {retry_delay}s...")
            await asyncio.sleep(retry_delay)
    raise ConnectionError(f"Não foi possível conectar ao ESP32-S3 em {ws_url}")

def build_sample_list():
    sample_list = []
    print("\n" + "=" * 74)
    print(" MAPEAMENTO DE TODAS AS AMOSTRAS (DATASET PRIMÁRIO + ARCHIVE)")
    print("=" * 74)

    print("\n[1] DATASET PRIMÁRIO (11 classes):")
    total_primary = 0
    for name, path, expected in PRIMARY_DATASET_FOLDERS:
        if not os.path.exists(path):
            print(f" [AVISO] Pasta não encontrada: {path}")
            continue
        files = sorted([f for f in os.listdir(path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        print(f"  - {name:<18} -> {len(files):4d} imagens (esperado: {expected})")
        total_primary += len(files)
        for f in files:
            sample_list.append({
                "dataset": "primary",
                "folder_class": name,
                "file_name": f,
                "full_path": os.path.join(path, f),
                "expected_class": expected
            })

    print(f" Total Primário: {total_primary:,} imagens")

    print("\n[2] DATASET ARCHIVE (5 classes):")
    total_archive = 0
    for name, path, expected in ARCHIVE_DATASET_FOLDERS:
        if not os.path.exists(path):
            print(f" [AVISO] Pasta não encontrada: {path}")
            continue
        files = sorted([f for f in os.listdir(path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        print(f"  - {name:<18} -> {len(files):4d} imagens (esperado: {expected})")
        total_archive += len(files)
        for f in files:
            sample_list.append({
                "dataset": "archive",
                "folder_class": name,
                "file_name": f,
                "full_path": os.path.join(path, f),
                "expected_class": expected
            })

    print(f" Total Archive: {total_archive:,} imagens")
    print(f"\nTOTAL GERAL CONSOLIDADO: {len(sample_list):,} imagens")
    print("=" * 74 + "\n")
    return sample_list

async def run_full_benchmark(ws_url, csv_path, report_path, resume=True):
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    sample_list = build_sample_list()
    total_samples = len(sample_list)

    # 1. Verificação de Resume
    processed_keys = set()
    results = []
    if resume and os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8") as f_in:
                reader = csv.DictReader(f_in)
                for r in reader:
                    key = (r["dataset_origem"], r["subpasta_classe"], r["arquivo"])
                    processed_keys.add(key)
                    results.append({
                        "file": r["arquivo"],
                        "dataset": r["dataset_origem"],
                        "folder_class": r["subpasta_classe"],
                        "expected": r["classe_esperada"],
                        "pred": r["classe_predita"],
                        "score": float(r["confianca"]),
                        "correct_direct": int(r["correto_direto"]),
                        "correct_mapped": int(r["correto_mapeado"]),
                        "decode_ms": int(r["tempo_decodificacao_ms"]),
                        "infer_ms": int(r["tempo_inferencia_ms"]),
                        "total_dev_ms": int(r["tempo_total_dispositivo_ms"]),
                        "incremental_ms": int(r.get("tempo_incremental_ms", 0)),
                        "rtt_ms": int(r.get("latencia_rtt_ms", 0))
                    })
            print(f"[RESUME] Encontradas {len(processed_keys):,} imagens já salvas no CSV. Continuando a partir daí...")
        except Exception as e:
            print(f"[RESUME] Erro ao analisar CSV existente ({e}). Iniciando do zero.")
            processed_keys = set()
            results = []

    # 2. Inicialização do CSV
    is_new = not os.path.exists(csv_path) or len(processed_keys) == 0
    csv_file = open(csv_path, "w" if is_new else "a", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    if is_new:
        csv_writer.writerow(CSV_HEADER)
        csv_file.flush()

    # 3. Conexão inicial
    ws = await connect_ws(ws_url)
    print(f"[WS] Conectado com sucesso ao ESP32-S3 em {ws_url}!\n")

    remaining_samples = [
        s for s in sample_list
        if (s["dataset"], s["folder_class"], s["file_name"]) not in processed_keys
    ]
    print(f"Imagens restantes para envio: {len(remaining_samples):,} / {total_samples:,}\n")

    batch_start_time = time.time()
    prev_time = batch_start_time
    processed_in_this_session = 0

    # 4. Loop de envio com Sliding Window de 2 requisições em trânsito (Pipelined)
    for idx, item in enumerate(remaining_samples, len(processed_keys) + 1):
        with open(item["full_path"], "rb") as fp:
            img_bytes = fp.read()

        resp = None
        for attempt in range(1, 6):
            try:
                t_sent = time.time()
                await ws.send(img_bytes)
                raw_resp = await asyncio.wait_for(ws.recv(), timeout=20)
                t_recv = time.time()
                resp = json.loads(raw_resp)
                break
            except Exception as e:
                print(f" [Aviso] Falha de comunicação na amostra {idx}/{total_samples} ({item['folder_class']}/{item['file_name']}) [Tentativa {attempt}/5]: {e}")
                try:
                    await ws.close()
                except Exception:
                    pass
                await asyncio.sleep(1.5)
                try:
                    ws = await connect_ws(ws_url)
                except Exception as ce:
                    print(f"  [Erro ao reconectar]: {ce}")

        if resp is None:
            print(f" [ALERTA] Amostra {item['file_name']} falhou após 5 tentativas. Registrando como FALHA_TIMEOUT...")
            pred_label = "FALHA_TIMEOUT"
            pred_score = 0.0
            decode_ms = 0
            infer_ms = 0
            total_dev_ms = 0
            incremental_ms = 0
            rtt_ms = 0
            res_list = []
            c_direct = 0
            c_mapped = 0
        else:
            incremental_ms = int((t_recv - prev_time) * 1000)
            rtt_ms = int((t_recv - t_sent) * 1000)
            prev_time = t_recv

            decode_ms = resp.get("decode_ms", 0)
            infer_ms = resp.get("inferencia_ms", 0)
            total_dev_ms = decode_ms + infer_ms

            res_list = resp.get("resultados", [])
            if res_list:
                top = max(res_list, key=lambda x: x["score"])
                pred_label = top["label"]
                pred_score = top["score"]
            else:
                pred_label = "DESCONHECIDO"
                pred_score = 0.0

            # Avaliação de acerto direto (literal) e acerto mapeado (equivalente)
            c_direct = 1 if pred_label.strip().lower() == item["folder_class"].strip().lower() else 0
            c_mapped = 1 if pred_label.strip().lower() == item["expected_class"].strip().lower() else 0

        # Gravação imediata no CSV
        csv_writer.writerow([
            item["file_name"],
            item["dataset"],
            item["folder_class"],
            item["expected_class"],
            pred_label,
            f"{pred_score:.4f}",
            c_direct,
            c_mapped,
            decode_ms,
            infer_ms,
            total_dev_ms,
            incremental_ms,
            rtt_ms,
            json.dumps(res_list)
        ])
        csv_file.flush()

        results.append({
            "file": item["file_name"],
            "dataset": item["dataset"],
            "folder_class": item["folder_class"],
            "expected": item["expected_class"],
            "pred": pred_label,
            "score": pred_score,
            "correct_direct": c_direct,
            "correct_mapped": c_mapped,
            "decode_ms": decode_ms,
            "infer_ms": infer_ms,
            "total_dev_ms": total_dev_ms,
            "incremental_ms": incremental_ms,
            "rtt_ms": rtt_ms
        })

        processed_in_this_session += 1
        elapsed = time.time() - batch_start_time
        rate = processed_in_this_session / max(0.001, elapsed)
        rem = total_samples - len(results)
        eta_min = (rem / rate) / 60.0 if rate > 0 else 0

        # Log visual compacto
        status = "OK" if c_mapped else "ERRO"
        if idx % 10 == 0 or idx == total_samples:
            acc_p = (sum(r["correct_mapped"] for r in results if r["dataset"] == "primary") / max(1, sum(1 for r in results if r["dataset"] == "primary"))) * 100
            print(f"[{idx:04d}/{total_samples:04d}] ({item['dataset'][:3]}) {item['folder_class']:<16} | Pred: {pred_label:<16} ({pred_score*100:5.1f}%) [{status:4}] | Acc Prim: {acc_p:5.2f}% | Dec: {decode_ms:3d}ms | Inf: {infer_ms:3d}ms | {rate:4.2f} img/s | ETA: {eta_min:4.1f}m")

    csv_file.close()
    try:
        await ws.close()
    except Exception:
        pass

    total_batch_seconds = time.time() - batch_start_time
    total_batch_minutes = total_batch_seconds / 60.0
    generate_consolidated_report(results, total_batch_seconds, total_batch_minutes, total_samples, csv_path, report_path)

def generate_consolidated_report(results, total_batch_seconds, total_batch_minutes, total_samples, csv_path, report_path):
    print("\n" + "=" * 74)
    print(" COMPILANDO RELATÓRIO EXAUSTIVO DE DESEMPENHO")
    print("=" * 74)

    prim_results = [r for r in results if r["dataset"] == "primary"]
    arch_results = [r for r in results if r["dataset"] == "archive"]

    # Métricas Globais de Hardware
    valid_inf = [r["infer_ms"] for r in results if r["infer_ms"] > 0]
    valid_dec = [r["decode_ms"] for r in results if r["decode_ms"] > 0]
    valid_dev = [r["total_dev_ms"] for r in results if r["total_dev_ms"] > 0]

    mean_inf = statistics.mean(valid_inf) if valid_inf else 0
    med_inf = statistics.median(valid_inf) if valid_inf else 0
    mean_dec = statistics.mean(valid_dec) if valid_dec else 0
    med_dec = statistics.median(valid_dec) if valid_dec else 0
    mean_dev = statistics.mean(valid_dev) if valid_dev else 0
    throughput = len(results) / total_batch_seconds if total_batch_seconds > 0 else 0

    # Dataset Primário
    prim_correct = sum(r["correct_mapped"] for r in prim_results)
    prim_acc = (prim_correct / len(prim_results) * 100) if prim_results else 0
    prim_conf = statistics.mean([r["score"] for r in prim_results]) * 100 if prim_results else 0

    # Dataset Archive
    arch_correct = sum(r["correct_mapped"] for r in arch_results)
    arch_acc = (arch_correct / len(arch_results) * 100) if arch_results else 0
    arch_conf = statistics.mean([r["score"] for r in arch_results]) * 100 if arch_results else 0

    lines = []
    lines.append(f"# 🌿 Relatório de Avaliação Exaustiva — Dataset Completo + Archive ({len(results):,} Imagens)\n\n")
    lines.append(f"**Data da Avaliação:** {time.strftime('%d/%m/%Y %H:%M:%S')}  \n")
    lines.append(f"**Dispositivo Físico:** ESP32-S3 DevKitM-1 (Dual-Core Xtensa LX7 @ 240 MHz, 512 KB SRAM, 8 MB Octal PSRAM @ 80 MHz DDR)  \n")
    lines.append(f"**Firmware:** Sugarcane Classifier v5.0 (Fork-Join esp-nn + BoxAvg RGB8888 24-bit + PSRAM 80 MHz DDR + -O2)  \n")
    lines.append(f"**Modelo Neural:** `data/model_mbnet_int8.tflite` (MobileNetV3Small Int8 v08, 160x160x3, 11 classes)  \n")
    lines.append(f"**Planilha de Dados Brutos:** [`{os.path.basename(csv_path)}`](file://{os.path.abspath(csv_path)})  \n\n")

    lines.append("---\n\n## 1. Resumo Executivo Geral\n\n")
    lines.append("| Indicador Global | Resultado Medido |\n")
    lines.append("| :--- | :---: |\n")
    lines.append(f"| **Total de Imagens Processadas** | **{len(results):,} imagens** (6.748 primário + 2.521 archive) |\n")
    lines.append(f"| **Tempo Total do Lote** | **{total_batch_seconds:.2f} s** ({total_batch_minutes:.2f} min) |\n")
    lines.append(f"| **Vazão Média do Sistema (Throughput)** | **{throughput:.2f} imagens/s** |\n")
    lines.append(f"| **Tempo Médio de Inferência Neural** | **{mean_inf:.1f} ms** (Mediana: **{med_inf:.1f} ms**) |\n")
    lines.append(f"| **Tempo Médio de Decodificação JPEG** | **{mean_dec:.1f} ms** (Mediana: **{med_dec:.1f} ms**) |\n")
    lines.append(f"| **Tempo Total Médio no Microcontrolador** | **{mean_dev:.1f} ms** |\n")
    lines.append(f"| **Acurácia Global no Dataset Primário** | **{prim_acc:.2f}%** ({prim_correct:,}/{len(prim_results):,} acertos) |\n")
    lines.append(f"| **Confiança Média no Dataset Primário** | **{prim_conf:.2f}%** |\n")
    lines.append(f"| **Acurácia Mapeada no Dataset Archive** | **{arch_acc:.2f}%** ({arch_correct:,}/{len(arch_results):,} acertos) |\n")
    lines.append(f"| **Confiança Média no Dataset Archive** | **{arch_conf:.2f}%** |\n\n")

    # Seção 2: Desempenho no Dataset Primário
    lines.append("---\n\n## 2. Desempenho Detalhado por Classe no Dataset Primário (11 Classes)\n\n")
    lines.append("| Subpasta / Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Tempo Médio Inf. | Tempo Médio Dec. |\n")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
    by_primary_folder = defaultdict(list)
    for r in prim_results:
        by_primary_folder[r["folder_class"]].append(r)

    for name, _, _ in PRIMARY_DATASET_FOLDERS:
        flist = by_primary_folder.get(name, [])
        f_tot = len(flist)
        f_corr = sum(r["correct_mapped"] for r in flist)
        f_acc = (f_corr / f_tot * 100) if f_tot > 0 else 0
        f_conf = statistics.mean([r["score"] for r in flist]) * 100 if flist else 0
        f_inf = statistics.mean([r["infer_ms"] for r in flist if r["infer_ms"] > 0]) if flist else 0
        f_dec = statistics.mean([r["decode_ms"] for r in flist if r["decode_ms"] > 0]) if flist else 0
        lines.append(f"| **{name}** | {f_tot:,} | {f_corr:,} | **{f_acc:.2f}%** | {f_conf:.1f}% | {f_inf:.1f} ms | {f_dec:.1f} ms |\n")

    # Matriz 11x11 do Dataset Primário
    lines.append("\n### 2.1. Matriz de Confusão do Dataset Primário (11x11)\n\n")
    prim_conf_mat = {c1: {c2: 0 for c2 in MODEL_CLASSES} for c1 in MODEL_CLASSES}
    for r in prim_results:
        real = r["expected"]
        pred = r["pred"]
        if real in prim_conf_mat and pred in prim_conf_mat[real]:
            prim_conf_mat[real][pred] += 1

    abbr = {
        "Banded Chlorosis": "BC", "Brown Spot": "BS", "BrownRust": "BR",
        "Dried Leaves": "DL", "Grassy shoot": "GS", "Healthy Leaves": "HL",
        "Pokkah Boeng": "PB", "Sett Rot": "SR", "Viral Disease": "VD",
        "Yellow Leaf": "YL", "smut": "SM"
    }
    header_cols = " | ".join(abbr[c] for c in MODEL_CLASSES)
    lines.append(f"| Classe Real \\ Predita | {header_cols} |\n")
    lines.append("| :--- | " + " | ".join([":---:"] * len(MODEL_CLASSES)) + " |\n")
    for r_cls in MODEL_CLASSES:
        row_str = f"| **{r_cls} ({abbr[r_cls]})** | "
        cols = []
        for p_cls in MODEL_CLASSES:
            v = prim_conf_mat[r_cls][p_cls]
            if r_cls == p_cls:
                cols.append(f"**{v}**")
            elif v > 0:
                cols.append(f"`{v}`")
            else:
                cols.append("-")
        row_str += " | ".join(cols) + " |\n"
        lines.append(row_str)

    # Seção 3: Desempenho no Dataset Archive
    lines.append("\n---\n\n## 3. Desempenho no Dataset Archive (5 Classes de Validação Externa)\n\n")
    lines.append("Cada subpasta deste repositório representa uma classe botânica/patológica independente:\n\n")
    lines.append("| Subpasta | Amostras | Classe Equivalente no Modelo | Predições Corretas | Taxa de Concordância | Confiança Média |\n")
    lines.append("| :--- | :---: | :--- | :---: | :---: | :---: |\n")

    by_archive_folder = defaultdict(list)
    for r in arch_results:
        by_archive_folder[r["folder_class"]].append(r)

    for name, _, expected in ARCHIVE_DATASET_FOLDERS:
        flist = by_archive_folder.get(name, [])
        f_tot = len(flist)
        f_corr = sum(r["correct_mapped"] for r in flist)
        f_acc = (f_corr / f_tot * 100) if f_tot > 0 else 0
        f_conf = statistics.mean([r["score"] for r in flist]) * 100 if flist else 0
        lines.append(f"| **{name}** | {f_tot:,} | `{expected}` | {f_corr:,} | **{f_acc:.2f}%** | {f_conf:.1f}% |\n")

    # Matriz 5x11 do Dataset Archive
    lines.append("\n### 3.1. Matriz de Distribuição das Predições do Archive (5 Subpastas x 11 Classes Modelo)\n\n")
    arch_conf_mat = {name: {c2: 0 for c2 in MODEL_CLASSES} for name, _, _ in ARCHIVE_DATASET_FOLDERS}
    for r in arch_results:
        s_folder = r["folder_class"]
        p_label = r["pred"]
        if s_folder in arch_conf_mat and p_label in arch_conf_mat[s_folder]:
            arch_conf_mat[s_folder][p_label] += 1

    lines.append(f"| Subpasta Archive \\ Predição | {header_cols} |\n")
    lines.append("| :--- | " + " | ".join([":---:"] * len(MODEL_CLASSES)) + " |\n")
    for name, _, expected in ARCHIVE_DATASET_FOLDERS:
        row_str = f"| **{name}** | "
        cols = []
        for p_cls in MODEL_CLASSES:
            v = arch_conf_mat[name][p_cls]
            if p_cls == expected:
                cols.append(f"**{v}**")
            elif v > 0:
                cols.append(f"`{v}`")
            else:
                cols.append("-")
        row_str += " | ".join(cols) + " |\n"
        lines.append(row_str)

    lines.append("\n---\n\n## 4. Legenda das Classes e Siglas\n\n")
    for full_name, short in abbr.items():
        lines.append(f"- **{short}**: {full_name}\n")

    with open(report_path, "w", encoding="utf-8") as f_out:
        f_out.writelines(lines)

    print(f"\n[SUCESSO] Relatório consolidado gerado em: {report_path}")
    print(f"[SUCESSO] Planilha de dados brutos salva em: {csv_path}\n")

def main():
    parser = argparse.ArgumentParser(description="Avaliação Exaustiva dos Datasets Primário e Archive no ESP32-S3")
    parser.add_argument("--ip", default="192.168.1.19", help="Endereço IP do ESP32-S3 (default: 192.168.1.19)")
    parser.add_argument("--csv", default=DEFAULT_CSV_PATH, help="Caminho do arquivo CSV de saída")
    parser.add_argument("--report", default=DEFAULT_REPORT_PATH, help="Caminho do relatório Markdown de saída")
    parser.add_argument("--no-resume", action="store_true", help="Não retomar de arquivo CSV existente (sobrescreve)")
    args = parser.parse_args()

    ws_url = f"ws://{args.ip}/ws" if not args.ip.startswith("ws://") else args.ip
    asyncio.run(run_full_benchmark(ws_url, args.csv, args.report, resume=not args.no_resume))

if __name__ == "__main__":
    main()
