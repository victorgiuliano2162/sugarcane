#!/usr/bin/env python3
"""
Script de Validação e Teste de Inferência do Modelo (Local TFLite ou Direto no ESP32-S3).

Uso Local (Emulação Python):
    python scripts/test_inference.py /caminho/para/folha.jpg
    python scripts/test_inference.py /caminho/para/pasta_de_imagens/

Uso no Hardware Real (via WebSocket no ESP32-S3):
    python scripts/test_inference.py /caminho/para/folha.jpg --esp32 192.168.1.19
"""

import sys
import os
import glob
import time
import json
import argparse

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "model_mbnet_int8.tflite")

LABELS = [
    "Banded Chlorosis", "Brown Spot", "BrownRust", "Dried Leaves",
    "Grassy shoot", "Healthy Leaves", "Pokkah Boeng", "Sett Rot",
    "Viral Disease", "Yellow Leaf", "smut"
]

def load_model():
    try:
        import tflite_runtime.interpreter as tflite
    except ImportError:
        try:
            import tensorflow.lite as tflite
        except ImportError:
            print("Erro: instale tflite-runtime ou tensorflow (pip install tflite-runtime Pillow numpy)")
            sys.exit(1)

    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"Modelo não encontrado em: {MODEL_PATH}")
    interpreter = tflite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    return interpreter

def preprocess_box_avg(image_path, target_size=(160, 160)):
    """
    Pré-processamento com Box Averaging (Image.Resampling.BOX).
    Garante paridade matemática com interpolation='area' do Keras e com a Opção C
    (Modo 7: RGB8888 + BoxAvg) implementada no firmware C++ do ESP32-S3.
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert('RGB')
    img = img.resize(target_size, Image.Resampling.BOX)
    arr = np.array(img, dtype=np.int32)
    # Quantização INT8 idêntica ao código C++ do ESP32: (pixel - 128)
    arr_int8 = (arr - 128).astype(np.int8)
    return np.expand_dims(arr_int8, axis=0)

def classify_local(interpreter, image_path):
    import numpy as np
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_tensor = preprocess_box_avg(image_path)

    start_time = time.perf_counter()
    interpreter.set_tensor(input_details[0]['index'], input_tensor)
    interpreter.invoke()
    output_data = interpreter.get_tensor(output_details[0]['index'])[0]
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    scale = output_details[0]['quantization_parameters']['scales'][0]
    zero_point = output_details[0]['quantization_parameters']['zero_points'][0]

    # Conversão INT8 para float (0.0 a 1.0)
    scores = (output_data.astype(np.float32) - zero_point) * scale
    scores = np.clip(scores, 0.0, 1.0)

    results = [(LABELS[i], float(scores[i])) for i in range(len(LABELS))]
    results.sort(key=lambda x: x[1], reverse=True)
    return results, elapsed_ms

async def classify_esp32_async(esp32_ip, image_path):
    import websockets
    ws_url = f"ws://{esp32_ip}/ws" if not esp32_ip.startswith("ws://") else esp32_ip
    with open(image_path, "rb") as fp:
        img_bytes = fp.read()

    t0 = time.perf_counter()
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        await ws.send(img_bytes)
        raw = await ws.recv()
    rtt_ms = (time.perf_counter() - t0) * 1000.0
    data = json.loads(raw)
    return data, rtt_ms

def main():
    parser = argparse.ArgumentParser(description="Classificador Foliar de Cana-de-Açúcar (Local ou ESP32-S3)")
    parser.add_argument("target", nargs="?", default="", help="Caminho do arquivo de imagem ou pasta de imagens")
    parser.add_argument("--esp32", default="", help="Endereço IP da placa ESP32-S3 (ex: 192.168.1.19)")
    parser.add_argument("--limit", type=int, default=10, help="Limite de imagens a processar se for pasta (default: 10)")
    args = parser.parse_args()

    # Seleção de alvo padrão
    target = args.target
    if not target:
        sample_cand = "/home/victor/Documents/datasets/Sugarcane leaf image dataset-20261106T004142Z-1-001/Sugarcane leaf image dataset/Healthy Leaves"
        if os.path.exists(sample_cand):
            target = sample_cand
            print(f"[INFO] Nenhum caminho informado. Usando pasta padrão: {target}\n")
        else:
            print("Uso: python scripts/test_inference.py <caminho_imagem_ou_pasta> [--esp32 IP]")
            sys.exit(1)

    if os.path.isdir(target):
        images = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            images.extend(glob.glob(os.path.join(target, ext)))
        images = sorted(images)[:args.limit]
    elif os.path.isfile(target):
        images = [target]
    else:
        print(f"Erro: Caminho não encontrado: {target}")
        sys.exit(1)

    if args.esp32:
        import asyncio
        print("=" * 72)
        print(f" CLASSIFICAÇÃO DIRETA NO HARDWARE ESP32-S3 (ws://{args.esp32}/ws)")
        print(f" Modo: Decodificação JPEG e Inferência TFLite Micro em C++")
        print("=" * 72)

        for img_path in images:
            img_name = os.path.basename(img_path)
            try:
                resp, rtt_ms = asyncio.run(classify_esp32_async(args.esp32, img_path))
                dec_ms = resp.get("decode_ms", 0)
                inf_ms = resp.get("inferencia_ms", 0)
                results = resp.get("resultados", [])
                results.sort(key=lambda x: x["score"], reverse=True)

                print(f"\nArquivo: {img_name}")
                print(f"Latência ESP32: Decode={dec_ms} ms | Inferência={inf_ms} ms | RTT Total={rtt_ms:.1f} ms")
                print("-" * 55)
                for rank, item in enumerate(results[:3], start=1):
                    score = item["score"]
                    bar = "█" * int(score * 30)
                    print(f"  {rank}º: {item['label']:<18} [{score*100:5.1f}%] {bar}")
            except Exception as e:
                print(f"\nArquivo: {img_name} -> Falha: {e}")
    else:
        interpreter = load_model()
        print("=" * 72)
        print(" CLASSIFICAÇÃO LOCAL VIA TFLITE RUNTIME (Emulação Python)")
        print(" Pré-processamento: Image.Resampling.BOX (Box Averaging com paridade C++)")
        print("=" * 72)

        for img_path in images:
            results, latency = classify_local(interpreter, img_path)
            img_name = os.path.basename(img_path)
            print(f"\nArquivo: {img_name} (Inferência Local: {latency:.2f} ms)")
            print("-" * 55)
            for rank, (label, score) in enumerate(results[:3], start=1):
                bar = "█" * int(score * 30)
                print(f"  {rank}º: {label:<18} [{score*100:5.1f}%] {bar}")

if __name__ == "__main__":
    main()
