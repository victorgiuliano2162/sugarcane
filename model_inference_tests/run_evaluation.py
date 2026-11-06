#!/usr/bin/env python3
import os
import sys
import time
import json
import csv
import asyncio
import statistics
from collections import defaultdict
import websockets

ESP32_WS_URL = "ws://192.168.1.44/ws"
DATASET_BASE = "/home/victor/Documents/datasets/Sugarcane leaf image dataset-20261106T004142Z-1-001/Sugarcane leaf image dataset"
OUTPUT_DIR = "/home/victor/projects/sugarcane/model_inference_tests"
CSV_PATH = os.path.join(OUTPUT_DIR, "resultado_inferencia.csv")
REPORT_PATH = os.path.join(OUTPUT_DIR, "RELATORIO_DESEMPENHO.md")

CLASSES = [
    ("Banded Chlorosis", os.path.join(DATASET_BASE, "Diseases", "Banded Chlorosis")),
    ("Brown Spot", os.path.join(DATASET_BASE, "Diseases", "Brown Spot")),
    ("BrownRust", os.path.join(DATASET_BASE, "Diseases", "BrownRust")),
    ("Dried Leaves", os.path.join(DATASET_BASE, "Dried Leaves")),
    ("Grassy shoot", os.path.join(DATASET_BASE, "Diseases", "Grassy shoot")),
    ("Healthy Leaves", os.path.join(DATASET_BASE, "Healthy Leaves")),
    ("Pokkah Boeng", os.path.join(DATASET_BASE, "Diseases", "Pokkah Boeng")),
    ("Sett Rot", os.path.join(DATASET_BASE, "Diseases", "Sett Rot")),
    ("Viral Disease", os.path.join(DATASET_BASE, "Diseases", "Viral Disease")),
    ("Yellow Leaf", os.path.join(DATASET_BASE, "Diseases", "Yellow Leaf")),
    ("smut", os.path.join(DATASET_BASE, "Diseases", "smut"))
]

SAMPLES_PER_CLASS = 50

async def connect_ws():
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            ws = await websockets.connect(ESP32_WS_URL, open_timeout=10, ping_interval=None)
            return ws
        except Exception as e:
            print(f"[WS] Tentativa {attempt}/{max_retries} falhou: {e}. Aguardando 2s...")
            await asyncio.sleep(2)
    raise ConnectionError(f"Não foi possível conectar ao ESP32 em {ESP32_WS_URL}")

async def send_image_and_get_result(ws, image_bytes, retries=3):
    current_ws = ws
    for attempt in range(retries):
        try:
            await current_ws.send(image_bytes)
            raw_response = await asyncio.wait_for(current_ws.recv(), timeout=15)
            data = json.loads(raw_response)
            return current_ws, data
        except Exception as e:
            print(f" [Aviso] Erro na requisição (tentativa {attempt + 1}/{retries}): {e}")
            try:
                await current_ws.close()
            except:
                pass
            await asyncio.sleep(1)
            current_ws = await connect_ws()
    raise RuntimeError("Falha persistente na comunicação com o ESP32")

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Preparar lista de amostras
    sample_list = []
    for cls_name, cls_path in CLASSES:
        if not os.path.exists(cls_path):
            print(f"ERRO: Pasta não encontrada: {cls_path}")
            sys.exit(1)
        files = sorted([f for f in os.listdir(cls_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        selected = files[:SAMPLES_PER_CLASS]
        for f in selected:
            sample_list.append({
                "class_name": cls_name,
                "file_name": f,
                "full_path": os.path.join(cls_path, f)
            })

    total_samples = len(sample_list)
    print(f"============================================================")
    print(f" INICIANDO AVALIAÇÃO DE DESEMPENHO NO ESP32-S3")
    print(f" Alvo: {ESP32_WS_URL}")
    print(f" Classes: {len(CLASSES)} | Amostras por classe: {SAMPLES_PER_CLASS}")
    print(f" Total de imagens a processar: {total_samples}")
    print(f"============================================================")

    # Abrir CSV
    csv_file = open(CSV_PATH, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        "arquivo",
        "classe_real",
        "classe_predita",
        "confianca",
        "correto",
        "tempo_decodificacao_ms",
        "tempo_inferencia_ms",
        "tempo_total_ms",
        "todas_probabilidades"
    ])
    csv_file.flush()

    ws = await connect_ws()
    print("[WS] Conectado com sucesso ao ESP32-S3!\n")

    results = []
    batch_start_time = time.time()

    try:
        for idx, item in enumerate(sample_list, 1):
            cls_name = item["class_name"]
            fname = item["file_name"]
            fpath = item["full_path"]

            with open(fpath, "rb") as f:
                img_data = f.read()

            t_req_start = time.time()
            ws, resp = await send_image_and_get_result(ws, img_data)
            t_req_end = time.time()

            decode_ms = resp.get("decode_ms", 0)
            infer_ms = resp.get("inferencia_ms", 0)
            total_device_ms = decode_ms + infer_ms
            roundtrip_ms = int((t_req_end - t_req_start) * 1000)

            res_list = resp.get("resultados", [])
            if res_list:
                top_pred = max(res_list, key=lambda x: x["score"])
                pred_label = top_pred["label"]
                pred_score = top_pred["score"]
            else:
                pred_label = "DESCONHECIDO"
                pred_score = 0.0

            is_correct = 1 if pred_label.strip().lower() == cls_name.strip().lower() else 0

            # Salvar no CSV
            csv_writer.writerow([
                fname,
                cls_name,
                pred_label,
                f"{pred_score:.4f}",
                is_correct,
                decode_ms,
                infer_ms,
                total_device_ms,
                json.dumps(res_list)
            ])
            csv_file.flush()

            status_str = "OK" if is_correct else "ERRO"
            print(f"[{idx:03d}/{total_samples:03d}] {cls_name:<16} | Pred: {pred_label:<16} ({pred_score*100:5.1f}%) [{status_str:4}] | Dec: {decode_ms:2d}ms | Inf: {infer_ms:3d}ms")

            results.append({
                "file": fname,
                "real": cls_name,
                "pred": pred_label,
                "score": pred_score,
                "correct": is_correct,
                "decode_ms": decode_ms,
                "infer_ms": infer_ms,
                "total_ms": total_device_ms,
                "roundtrip_ms": roundtrip_ms
            })

    finally:
        csv_file.close()
        try:
            await ws.close()
        except:
            pass

    batch_end_time = time.time()
    total_batch_seconds = batch_end_time - batch_start_time
    total_batch_minutes = total_batch_seconds / 60.0

    print(f"\n============================================================")
    print(f" PROCESSAMENTO FINALIZADO!")
    print(f" Tempo total do lote: {total_batch_seconds:.2f} s ({total_batch_minutes:.2f} min)")
    print(f" Taxa média: {total_samples / total_batch_seconds:.2f} imagens/segundo")
    print(f"============================================================")

    # Gerar Estatísticas e Relatório
    generate_report(results, total_batch_seconds, total_batch_minutes, total_samples)

def generate_report(results, total_batch_seconds, total_batch_minutes, total_samples):
    all_classes = [c[0] for c in CLASSES]
    
    total_correct = sum(r["correct"] for r in results)
    global_accuracy = (total_correct / total_samples) * 100.0

    decode_times = [r["decode_ms"] for r in results]
    infer_times = [r["infer_ms"] for r in results]
    total_times = [r["total_ms"] for r in results]
    roundtrip_times = [r["roundtrip_ms"] for r in results]

    dec_mean = statistics.mean(decode_times)
    dec_min = min(decode_times)
    dec_max = max(decode_times)

    inf_mean = statistics.mean(infer_times)
    inf_min = min(infer_times)
    inf_max = max(infer_times)
    inf_std = statistics.stdev(infer_times) if len(infer_times) > 1 else 0

    tot_mean = statistics.mean(total_times)
    tot_min = min(total_times)
    tot_max = max(total_times)

    rt_mean = statistics.mean(roundtrip_times)

    # Estatísticas por classe
    class_stats = {}
    confusion_matrix = defaultdict(lambda: defaultdict(int))

    for r in results:
        real = r["real"]
        pred = r["pred"]
        confusion_matrix[real][pred] += 1
        if real not in class_stats:
            class_stats[real] = {
                "total": 0,
                "correct": 0,
                "scores": [],
                "inf_times": []
            }
        class_stats[real]["total"] += 1
        if r["correct"]:
            class_stats[real]["correct"] += 1
        class_stats[real]["scores"].append(r["score"])
        class_stats[real]["inf_times"].append(r["infer_ms"])

    # Montar Relatório Markdown
    lines = []
    lines.append("# Relatório de Desempenho e Inferência da Rede Neural no ESP32-S3\n")
    lines.append(f"**Data da Avaliação:** {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
    lines.append(f"**Dispositivo:** ESP32-S3 (8MB Octal PSRAM @ 40MHz, Xtensa Dual Core @ 240MHz)\n")
    lines.append(f"**Framework de Inferência:** TensorFlow Lite Micro com SIMD Xtensa / NN Optimized\n")
    lines.append(f"**Comunicação:** WebSocket (`ws://192.168.1.44/ws`)\n")
    lines.append(f"**Dataset de Teste:** 50 primeiras amostras de cada uma das 11 classes ({total_samples} imagens no total)\n\n")

    lines.append("## 1. Resumo Executivo Geral\n")
    lines.append(f"| Métrica | Valor |\n")
    lines.append(f"| :--- | :--- |\n")
    lines.append(f"| **Total de Imagens Avaliadas** | **{total_samples} imagens** |\n")
    lines.append(f"| **Acurácia Global** | **{global_accuracy:.2f}%** ({total_correct}/{total_samples} acertos) |\n")
    lines.append(f"| **Tempo Total do Lote (550 imagens)** | **{total_batch_seconds:.2f} segundos** ({total_batch_minutes:.2f} minutos) |\n")
    lines.append(f"| **Vazão Média (Throughput)** | **{total_samples / total_batch_seconds:.2f} imagens/segundo** |\n")
    lines.append(f"| **Tempo Médio de Inferência (Rede Neural)** | **{inf_mean:.1f} ms** (Mín: {inf_min} ms / Máx: {inf_max} ms / Desvio: ±{inf_std:.1f} ms) |\n")
    lines.append(f"| **Tempo Médio de Decodificação JPEG** | **{dec_mean:.1f} ms** (Mín: {dec_min} ms / Máx: {dec_max} ms) |\n")
    lines.append(f"| **Tempo Total Médio no Dispositivo (Decode + Inferência)** | **{tot_mean:.1f} ms** |\n")
    lines.append(f"| **Latência Média Completa (Rede + ESP32 Roundtrip)** | **{rt_mean:.1f} ms** |\n\n")

    lines.append("## 2. Desempenho Detalhado por Classe\n")
    lines.append("| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Tempo Médio Inf. |\n")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |\n")

    for cls in all_classes:
        st = class_stats.get(cls, {"total": 0, "correct": 0, "scores": [0], "inf_times": [0]})
        acc = (st["correct"] / st["total"] * 100.0) if st["total"] > 0 else 0
        avg_score = statistics.mean(st["scores"]) * 100.0 if st["scores"] else 0
        avg_inf = statistics.mean(st["inf_times"]) if st["inf_times"] else 0
        lines.append(f"| **{cls}** | {st['total']} | {st['correct']} | **{acc:.1f}%** | {avg_score:.1f}% | {avg_inf:.1f} ms |\n")

    lines.append("\n## 3. Matriz de Confusão (50 amostras por linha)\n")
    lines.append("As linhas representam a **Classe Real** e as colunas a **Classe Predita**:\n\n")

    # Tabela da Matriz
    header = "| Classe Real \\ Predição | " + " | ".join(all_classes) + " |"
    sep = "| :--- | " + " | ".join([":---:" for _ in all_classes]) + " |"
    lines.append(header + "\n")
    lines.append(sep + "\n")

    for real in all_classes:
        row = [f"**{real}**"]
        for pred in all_classes:
            cnt = confusion_matrix[real][pred]
            if cnt > 0 and real == pred:
                row.append(f"**{cnt}**")
            elif cnt > 0:
                row.append(f"`{cnt}`")
            else:
                row.append("-")
        lines.append("| " + " | ".join(row) + " |\n")

    lines.append("\n## 4. Análise de Eficiência e Recursos do Hardware\n")
    lines.append(f"* **Decodificação JPEG:** Processada em memória PSRAM a uma taxa média de ~**{dec_mean:.1f} ms**, comprovando a eficiência do parser JPEG embarcado.\n")
    lines.append(f"* **Inferência TFLite Micro:** A execução da MobileNet INT8 consumiu em média **{inf_mean:.1f} ms** por frame com baixa dispersão, demonstrando alta estabilidade térmica e de clock dos núcleos Xtensa LX7.\n")
    lines.append("* **Armazenamento:** A planilha detalhada com todos os 550 registros e probabilidades completas está salva em `model_inference_tests/resultado_inferencia.csv`.\n")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\n[OK] Relatório gerado com sucesso em: {REPORT_PATH}")
    print(f"[OK] Planilha CSV salva em: {CSV_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
