#!/usr/bin/env python3
"""
Script de Validação e Teste de Inferência do Modelo TFLite INT8 (sem embarcar na ESP32).
Uso:
    python scripts/test_inference.py <caminho_da_imagem>
    python scripts/test_inference.py /caminho/para/pasta_de_imagens/
"""

import sys
import os
import glob
import time
import numpy as np
from PIL import Image

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        print("Erro: instale tflite-runtime ou tensorflow (ex: pip install tflite-runtime Pillow numpy)")
        sys.exit(1)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "model_mbnet_int8.tflite")

LABELS = [
    "Banded Chlorosis", "Brown Spot", "BrownRust", "Dried Leaves",
    "Grassy shoot", "Healthy Leaves", "Pokkah Boeng", "Sett Rot",
    "Viral Disease", "Yellow Leaf", "smut"
]

def load_model():
    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"Modelo não encontrado em: {MODEL_PATH}")
    interpreter = tflite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    return interpreter

def preprocess(image_path, target_size=(160, 160)):
    """Simula com precisão o pipeline de decodificação JPEG e pré-processamento INT8 da ESP32."""
    img = Image.open(image_path).convert('RGB')
    img = img.resize(target_size, Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.int32)
    # Quantização INT8 idêntica ao código C++ do ESP32: (pixel - 128)
    arr_int8 = (arr - 128).astype(np.int8)
    return np.expand_dims(arr_int8, axis=0)

def classify_image(interpreter, image_path):
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    input_tensor = preprocess(image_path)
    
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

def main():
    if len(sys.argv) < 2:
        target = "/home/victor/Documents/sugar-cane/archive/Healthy"
        print(f"Nenhum arquivo informado. Usando imagens de exemplo em: {target}\n")
    else:
        target = sys.argv[1]
    
    interpreter = load_model()
    
    if os.path.isdir(target):
        images = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            images.extend(glob.glob(os.path.join(target, ext)))
        images = sorted(images)[:10]
    elif os.path.isfile(target):
        images = [target]
    else:
        print(f"Caminho não encontrado: {target}")
        sys.exit(1)
        
    print("=" * 70)
    print(" RESULTADO DA INFERÊNCIA DO MODELO TFLITE (MobileNetV2 INT8)")
    print("=" * 70)
    
    for img_path in images:
        results, latency = classify_image(interpreter, img_path)
        img_name = os.path.basename(img_path)
        print(f"\nArquivo: {img_name} (Latência de Inferência: {latency:.2f} ms)")
        print("-" * 50)
        for rank, (label, score) in enumerate(results[:3], start=1):
            bar = "█" * int(score * 30)
            print(f"  {rank}º: {label:<18} [{score*100:5.1f}%] {bar}")

if __name__ == "__main__":
    main()
