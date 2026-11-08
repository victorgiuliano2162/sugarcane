#!/usr/bin/env python3
"""
Bancada de Co-Simulação Hardware-in-the-Loop (HIL) MAVLink para Payload Agrícola ESP32-S3.

Simula a dinâmica de voo tridimensional de um VANT sobre um talhão de cana-de-açúcar,
gerando telemetria MAVLink v2 (HEARTBEAT, GLOBAL_POSITION_INT, ATTITUDE), executando
a máquina de estados de Parada Amostral Sistemática (Pause-and-Classify) e injetando
imagens foliares em tempo real via WebSocket na placa física ESP32-S3.

Uso Típico:
    python scripts/hil_mavlink_simulator.py --esp32 192.168.1.19
    python scripts/hil_mavlink_simulator.py --esp32 192.168.1.19 --waypoints 55 --mavlink-out udpout:127.0.0.1:14550
"""

import sys
import os
import time
import math
import json
import glob
import random
import asyncio
import argparse
from datetime import datetime

try:
    import websockets
except ImportError:
    print("[ERRO] Biblioteca 'websockets' não encontrada. Instale com: pip install websockets")
    sys.exit(1)

try:
    from pymavlink import mavutil
except ImportError:
    print("[ERRO] Biblioteca 'pymavlink' não encontrada. Instale com: pip install pymavlink")
    sys.exit(1)

# ==============================================================================
# CONFIGURAÇÕES AGRONÔMICAS E DE COORDENADAS (Ribeirão Preto / SP)
# ==============================================================================
DEFAULT_LAT = -21.177500   # Centro do Talhão 04
DEFAULT_LON = -47.810300
DEFAULT_ALT_MSL = 580.0    # Altitude ao nível do mar (metros)
DEFAULT_ALT_AGL = 15.0     # Altitude de sobrevoo sobre a copa (metros)
DEFAULT_SPEED_MS = 5.0     # Velocidade de cruzeiro (m/s)
DEFAULT_STABILIZE_MS = 500 # Tempo de estabilização contra motion blur (ms)

DEFAULT_DATASET_DIR = "/home/victor/Documents/datasets/Sugarcane leaf image dataset-20261106T004142Z-1-001/Sugarcane leaf image dataset"

LABELS_11 = [
    "Banded Chlorosis", "Brown Spot", "BrownRust", "Dried Leaves",
    "Grassy shoot", "Healthy Leaves", "Pokkah Boeng", "Sett Rot",
    "Viral Disease", "Yellow Leaf", "smut"
]

# Severidade de risco agronômico (0 = normal/saudável, 1 = moderado, 2 = crítico/epidêmico)
SEVERITY_MAP = {
    "Healthy Leaves": 0,
    "Dried Leaves": 0,
    "Banded Chlorosis": 1,
    "Brown Spot": 1,
    "Grassy shoot": 1,
    "Pokkah Boeng": 1,
    "Sett Rot": 1,
    "Viral Disease": 1,
    "Yellow Leaf": 1,
    "BrownRust": 2,  # Ferrugem Marrom (quarentenária / alto dano)
    "smut": 2        # Carvão da Cana (alto poder destrutivo / dispersão aérea)
}


class SugarcaneFieldGrid:
    """
    Gera a grade de amostragem no talhão e faz a distribuição agronômica
    realista de focos de patógenos (reboleiras de Carvão e Ferrugem).
    """
    def __init__(self, center_lat, center_lon, rows=5, cols=11, row_spacing_m=25.0, col_spacing_m=18.0):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.rows = rows
        self.cols = cols
        self.row_spacing_m = row_spacing_m
        self.col_spacing_m = col_spacing_m

        # Conversão aproximada metros -> graus lat/lon em ~21°S
        # 1 grau lat ~ 110.7 km
        # 1 grau lon ~ 111.3 * cos(-21.18°) ~ 103.8 km
        self.lat_m_to_deg = 1.0 / 110700.0
        self.lon_m_to_deg = 1.0 / (111320.0 * math.cos(math.radians(center_lat)))

        self.waypoints = self._generate_grid()

    def _generate_grid(self):
        wps = []
        wp_id = 1
        total_width = (self.cols - 1) * self.col_spacing_m
        total_height = (self.rows - 1) * self.row_spacing_m

        start_lat = self.center_lat - (total_height / 2.0) * self.lat_m_to_deg
        start_lon = self.center_lon - (total_width / 2.0) * self.lon_m_to_deg

        for r in range(self.rows):
            # Padrão serpentina (vai-e-vem)
            cols_range = range(self.cols) if (r % 2 == 0) else range(self.cols - 1, -1, -1)
            for c in cols_range:
                lat = start_lat + (r * self.row_spacing_m) * self.lat_m_to_deg
                lon = start_lon + (c * self.col_spacing_m) * self.lon_m_to_deg

                # Distribuição epidemiológica com focos aglomerados (reboleiras)
                # Reboleira de Carvão (smut): Quadrante Nordeste (linhas 3,4, colunas 7..10)
                # Reboleira de Ferrugem (BrownRust): Linhas 0,1, colunas 7..10
                # Faixa amarelada / clorose / seca: bordas
                # Miolo do talhão: canavial saudável dominante (Healthy Leaves)
                assigned_class = self._assign_disease_class(r, c)

                wps.append({
                    "id": wp_id,
                    "row": r,
                    "col": c,
                    "lat": lat,
                    "lon": lon,
                    "target_class": assigned_class
                })
                wp_id += 1
        return wps

    def _assign_disease_class(self, r, c):
        # Foco de Carvão (smut) nas linhas 3 e 4, colunas 7 a 10
        if r >= 3 and c >= 7:
            return "smut"
        # Foco de Ferrugem Marrom (BrownRust) nas linhas 0 e 1, colunas 7 a 10
        if r <= 1 and c >= 7:
            return "BrownRust"
        # Manchas e cloroses na transição (coluna 6)
        if c == 6:
            return random.choice(["Yellow Leaf", "Banded Chlorosis", "Brown Spot"])
        # Estresse de bordadura na coluna 0
        if c == 0:
            return random.choice(["Dried Leaves", "Yellow Leaf", "Pokkah Boeng"])
        # Outras patologias esparsas
        if (r, c) == (2, 2):
            return "Grassy shoot"
        if (r, c) == (2, 4):
            return "Sett Rot"
        if (r, c) == (1, 3):
            return "Viral Disease"
        # Cana predominantemente saudável no restante do talhão
        return "Healthy Leaves"


class DatasetSampler:
    """
    Localiza e seleciona imagens reais correspondentes a cada classe de patógeno.
    """
    def __init__(self, dataset_base_dir):
        self.base_dir = dataset_base_dir
        self.class_images = {}
        self._index_dataset()

    def _index_dataset(self):
        if not os.path.isdir(self.base_dir):
            print(f"[AVISO] Pasta do dataset não encontrada: {self.base_dir}")
            return

        for label in LABELS_11:
            imgs = []
            # Verifica pasta direta ou subpasta Diseases
            direct_path = os.path.join(self.base_dir, label)
            diseases_path = os.path.join(self.base_dir, "Diseases", label)
            
            search_path = direct_path if os.path.isdir(direct_path) else diseases_path
            if os.path.isdir(search_path):
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
                    imgs.extend(glob.glob(os.path.join(search_path, ext)))
            self.class_images[label] = sorted(imgs)
            # print(f"  [Index] {label:20s}: {len(imgs)} imagens")

    def get_sample_image(self, label, sample_index=0):
        imgs = self.class_images.get(label, [])
        if not imgs:
            return None
        idx = sample_index % len(imgs)
        return imgs[idx]


class HilMavlinkSimulator:
    """
    Motor de co-simulação MAVLink com execução da máquina de estados Pause-and-Classify.
    """
    def __init__(self, args):
        self.args = args
        self.esp32_ip = args.esp32
        self.ws_url = f"ws://{args.esp32}/ws" if args.esp32 and not args.esp32.startswith("ws://") else args.esp32
        self.mavlink_conn_str = args.mavlink_out
        self.mav = None
        self.speed = args.speed
        self.alt_agl = args.alt
        self.alt_msl = DEFAULT_ALT_MSL + self.alt_agl
        self.stabilize_ms = args.stabilize_ms

        self.grid = SugarcaneFieldGrid(
            center_lat=args.field_lat,
            center_lon=args.field_lon,
            rows=args.rows,
            cols=args.cols,
            row_spacing_m=args.row_spacing,
            col_spacing_m=args.col_spacing
        )

        self.sampler = DatasetSampler(args.dataset_dir)
        self.records = []

        # Estado da aeronave simulada
        self.current_lat = self.grid.waypoints[0]["lat"]
        self.current_lon = self.grid.waypoints[0]["lon"]
        self.current_alt_msl = self.alt_msl
        self.current_alt_agl = 0.0
        self.current_speed = 0.0
        self.current_heading_deg = 0.0
        self.boot_time_s = time.time()
        self.system_id = 1
        self.component_id = 1

    def init_mavlink(self):
        if self.mavlink_conn_str and self.mavlink_conn_str.lower() != "none":
            try:
                print(f"[MAVLink] Inicializando conexão de telemetria em: {self.mavlink_conn_str}")
                self.mav = mavutil.mavlink_connection(
                    self.mavlink_conn_str,
                    source_system=self.system_id,
                    source_component=self.component_id
                )
                print("[MAVLink] Enlace MAVLink ativo e pronto.")
            except Exception as e:
                print(f"[MAVLink] Aviso: não foi possível iniciar enlace MAVLink ({e}). Continuando em modo autônomo.")
                self.mav = None

    def send_mavlink_telemetry(self, is_paused=False):
        if not self.mav:
            return

        time_boot_ms = int((time.time() - self.boot_time_s) * 1000)

        # 1. HEARTBEAT (1 Hz aproximado ou chamado durante loop)
        self.mav.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR,
            mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
            mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED | mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            3 if is_paused else 4, # Custom mode: LOITER / AUTO
            mavutil.mavlink.MAV_STATE_ACTIVE
        )

        # 2. GLOBAL_POSITION_INT (10 Hz)
        # Lat/Lon em degE7, alt em mm, velocidades em cm/s, heading em cdeg
        vx_cms = int(self.current_speed * math.cos(math.radians(self.current_heading_deg)) * 100)
        vy_cms = int(self.current_speed * math.sin(math.radians(self.current_heading_deg)) * 100)
        vz_cms = 0

        self.mav.mav.global_position_int_send(
            time_boot_ms,
            int(self.current_lat * 1e7),
            int(self.current_lon * 1e7),
            int(self.current_alt_msl * 1000),
            int(self.current_alt_agl * 1000),
            vx_cms,
            vy_cms,
            vz_cms,
            int(self.current_heading_deg * 100)
        )

        # 3. ATTITUDE
        roll = 0.0
        pitch = 0.0 if is_paused else 0.05 # leve inclinação frontal ao voar
        yaw = math.radians(self.current_heading_deg)
        self.mav.mav.attitude_send(
            time_boot_ms,
            roll,
            pitch,
            yaw,
            0.0, 0.0, 0.0
        )

    def send_mavlink_pause_command(self, pause=True):
        if not self.mav:
            return
        # MAV_CMD_DO_PAUSE_CONTINUE = 193 (param1: 1=pause, 0=resume)
        self.mav.mav.command_long_send(
            self.system_id,
            self.component_id,
            mavutil.mavlink.MAV_CMD_DO_PAUSE_CONTINUE,
            0,
            1.0 if pause else 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        )

    async def classify_on_esp32(self, image_path):
        """
        Envia o JPEG via WebSocket para a placa física ESP32-S3 e obtém a inferência.
        """
        if not self.ws_url or self.args.mock_esp32:
            # Modo simulado caso não haja placa conectada
            await asyncio.sleep(0.380)
            return {
                "status": "sucesso",
                "decode_ms": 102,
                "inferencia_ms": 283,
                "resultados": [{"label": "Healthy Leaves", "score": 0.92}]
            }, 385.0

        with open(image_path, "rb") as fp:
            img_bytes = fp.read()

        t0 = time.perf_counter()
        async with websockets.connect(self.ws_url, open_timeout=5, max_size=10*1024*1024) as ws:
            await ws.send(img_bytes)
            raw = await ws.recv()
        rtt_ms = (time.perf_counter() - t0) * 1000.0

        data = json.loads(raw)
        return data, rtt_ms

    async def run_mission(self):
        self.init_mavlink()
        total_wps = len(self.grid.waypoints)
        print("=" * 80)
        print("  INICIANDO MISSÃO HIL DE RECONHECIMENTO FITOSSANITÁRIO EM CANAVIAL")
        print(f"  Talhão Alvo: Lat {self.grid.center_lat:.6f}, Lon {self.grid.center_lon:.6f} (Ribeirão Preto/SP)")
        print(f"  Dimensões da Grade: {self.grid.rows} linhas x {self.grid.cols} pontos = {total_wps} waypoints")
        print(f"  Parâmetros de Voo: Altitude {self.alt_agl} m AGL, Velocidade {self.speed} m/s")
        print(f"  Enlace Payload: {self.ws_url} (Hardware Real ESP32-S3)")
        print(f"  Estratégia de Controle: Pause-and-Classify (Estabilização ~{self.stabilize_ms} ms)")
        print("=" * 80)

        # 1. Decolagem Simulada
        print("\n[VANT] Decolando para altitude de inspeção (15.0 m AGL)...")
        self.current_alt_agl = self.alt_agl
        self.current_alt_msl = DEFAULT_ALT_MSL + self.alt_agl
        self.send_mavlink_telemetry(is_paused=False)
        await asyncio.sleep(0.5)

        mission_start_time = time.time()
        dist_total_m = 0.0

        # Loop de Waypoints
        for idx, wp in enumerate(self.grid.waypoints):
            wp_num = wp["id"]
            target_lat = wp["lat"]
            target_lon = wp["lon"]
            target_cls = wp["target_class"]

            # Calcula distância e direção do voo
            d_lat_m = (target_lat - self.current_lat) / self.grid.lat_m_to_deg
            d_lon_m = (target_lon - self.current_lon) / self.grid.lon_m_to_deg
            leg_dist_m = math.hypot(d_lat_m, d_lon_m)
            dist_total_m += leg_dist_m

            if leg_dist_m > 0.01:
                self.current_heading_deg = (math.degrees(math.atan2(d_lon_m, d_lat_m)) + 360.0) % 360.0
            
            # --- FASE 1: NAVEGAÇÃO EM CRUZEIRO (5 m/s) ---
            flight_time_s = leg_dist_m / self.speed if self.speed > 0 else 0.5
            # Simulação rápida com amostragem de 10 Hz
            steps = max(2, int(flight_time_s * 4)) # acelerado para fluidez
            self.current_speed = self.speed

            for s in range(steps):
                alpha = (s + 1) / steps
                self.current_lat = self.current_lat + (target_lat - self.current_lat) * alpha
                self.current_lon = self.current_lon + (target_lon - self.current_lon) * alpha
                self.send_mavlink_telemetry(is_paused=False)
                await asyncio.sleep(0.02) # Passo de animação HIL

            self.current_lat = target_lat
            self.current_lon = target_lon

            # --- FASE 2: COMANDO DE PARADA AMOSTRAL (Pause-and-Classify) ---
            t_pause_start = time.perf_counter()
            self.send_mavlink_pause_command(pause=True)
            self.current_speed = 0.0
            self.send_mavlink_telemetry(is_paused=True)

            # Estabilização aerodinâmica (~500 ms)
            await asyncio.sleep(self.stabilize_ms / 1000.0)
            t_stabilize_actual_ms = (time.perf_counter() - t_pause_start) * 1000.0

            # --- FASE 3: AQUISIÇÃO E CLASSIFICAÇÃO NO ESP32-S3 ---
            img_path = self.sampler.get_sample_image(target_cls, sample_index=idx)
            if not img_path:
                print(f"[AVISO] Nenhuma imagem encontrada para classe '{target_cls}'!")
                continue

            resp, rtt_ms = await self.classify_on_esp32(img_path)

            decode_ms = resp.get("decode_ms", 0)
            inferencia_ms = resp.get("inferencia_ms", 0)
            resultados = resp.get("resultados", [])

            pred_class = "Desconhecido"
            confidence = 0.0
            if resultados:
                top = max(resultados, key=lambda x: x.get("score", 0))
                pred_class = top.get("label", "")
                confidence = top.get("score", 0.0)

            acerto = 1 if (pred_class == target_cls) else 0
            t_total_pause_ms = (time.perf_counter() - t_pause_start) * 1000.0

            # --- FASE 4: REGISTRO GEORREFERENCIADO ---
            record = {
                "timestamp_iso": datetime.now().isoformat(),
                "waypoint_id": wp_num,
                "row": wp["row"],
                "col": wp["col"],
                "lat": round(target_lat, 7),
                "lon": round(target_lon, 7),
                "alt_msl_m": round(self.current_alt_msl, 1),
                "alt_agl_m": round(self.current_alt_agl, 1),
                "heading_deg": round(self.current_heading_deg, 1),
                "groundspeed_ms": 0.0,
                "tempo_estabilizacao_ms": round(t_stabilize_actual_ms, 1),
                "tempo_decodificacao_ms": decode_ms,
                "tempo_inferencia_ms": inferencia_ms,
                "tempo_total_pausa_ms": round(t_total_pause_ms, 1),
                "classe_real": target_cls,
                "classe_predita": pred_class,
                "confianca": round(confidence, 4),
                "acerto": acerto,
                "severidade_risco": SEVERITY_MAP.get(pred_class, 1),
                "arquivo_imagem": os.path.basename(img_path),
                "todas_probabilidades": json.dumps(resultados)
            }
            self.records.append(record)

            # Exibição no Terminal
            status_symbol = "✓" if acerto else "✗"
            risk_tag = ""
            if pred_class == "smut":
                risk_tag = " [!! FOCO CARVÃO !!]"
            elif pred_class == "BrownRust":
                risk_tag = " [! FOCO FERRUGEM !]"

            print(f"[{wp_num:02d}/{total_wps:02d}] WP({wp['row']},{wp['col']}) "
                  f"Lat: {target_lat:.6f} Lon: {target_lon:.6f} | "
                  f"Real: {target_cls:15s} -> Pred: {pred_class:15s} ({confidence*100:5.1f}%) {status_symbol} | "
                  f"Dec: {decode_ms:3d}ms Inf: {inferencia_ms:3d}ms Ciclo: {t_total_pause_ms:4.0f}ms{risk_tag}")

            # --- FASE 5: DESBLOQUEIO E RETOMADA DO VOO ---
            self.send_mavlink_pause_command(pause=False)
            self.current_speed = self.speed
            self.send_mavlink_telemetry(is_paused=False)

        # 6. Fim da Missão e Pouso
        mission_duration_s = time.time() - mission_start_time
        print("\n[VANT] Missão concluída! Retornando ao ponto de lançamento e pousando...")
        self.current_alt_agl = 0.0
        self.current_speed = 0.0
        self.send_mavlink_telemetry(is_paused=True)

        self._save_results(mission_duration_s, dist_total_m)

    def _save_results(self, duration_s, distance_m):
        os.makedirs(os.path.dirname(self.args.output_csv), exist_ok=True)
        import csv

        fieldnames = [
            "timestamp_iso", "waypoint_id", "row", "col", "lat", "lon",
            "alt_msl_m", "alt_agl_m", "heading_deg", "groundspeed_ms",
            "tempo_estabilizacao_ms", "tempo_decodificacao_ms", "tempo_inferencia_ms",
            "tempo_total_pausa_ms", "classe_real", "classe_predita", "confianca",
            "acerto", "severidade_risco", "arquivo_imagem", "todas_probabilidades"
        ]

        # Salva no caminho solicitado e também copia para docs/heatmaps/
        target_paths = [self.args.output_csv, "docs/heatmaps/missao_hil_georreferenciada.csv"]

        for p in target_paths:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for rec in self.records:
                    writer.writerow(rec)

        # Estatísticas Globais
        total = len(self.records)
        acertos = sum(r["acerto"] for r in self.records)
        acc_pct = (acertos / total * 100.0) if total > 0 else 0.0
        avg_dec = sum(r["tempo_decodificacao_ms"] for r in self.records) / total if total > 0 else 0
        avg_inf = sum(r["tempo_inferencia_ms"] for r in self.records) / total if total > 0 else 0
        avg_pause = sum(r["tempo_total_pausa_ms"] for r in self.records) / total if total > 0 else 0
        smut_detected = sum(1 for r in self.records if r["classe_predita"] == "smut")
        rust_detected = sum(1 for r in self.records if r["classe_predita"] == "BrownRust")

        print("\n" + "=" * 80)
        print("  RELATÓRIO FINAL DA BANCADA DE CO-SIMULAÇÃO HIL")
        print("=" * 80)
        print(f"  • Pontos Inspecionados:     {total}")
        print(f"  • Distância Total Voo:       {distance_m:.1f} metros")
        print(f"  • Duração Total da Missão:  {duration_s:.1f} segundos ({duration_s/60.0:.2f} minutos)")
        print(f"  • Acurácia Global Hardware:  {acertos}/{total} ({acc_pct:.2f}%)")
        print(f"  • Tempo Médio Decodificação: {avg_dec:.1f} ms")
        print(f"  • Tempo Médio Inferência:    {avg_inf:.1f} ms (SIMD INT8 na Octal PSRAM + SRAM)")
        print(f"  • Tempo Médio Ciclo Parada:  {avg_pause:.1f} ms")
        print(f"  • Focos de Carvão (smut):    {smut_detected} pontos detectados")
        print(f"  • Focos Ferrugem (BrownRust):{rust_detected} pontos detectados")
        print(f"  • Logs CSV salvos em:        {self.args.output_csv}")
        print("=" * 80 + "\n")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Co-Simulador HIL MAVLink para Payload ESP32-S3")
    parser.add_argument("--esp32", default="192.168.1.19", help="IP do ESP32-S3 (default: 192.168.1.19)")
    parser.add_argument("--mock-esp32", action="store_true", help="Executa sem hardware real para testes")
    parser.add_argument("--mavlink-out", default="udpout:127.0.0.1:14550", help="Destino MAVLink UDP (ex: udpout:127.0.0.1:14550)")
    parser.add_argument("--rows", type=int, default=5, help="Número de linhas do grid (default: 5)")
    parser.add_argument("--cols", type=int, default=11, help="Número de colunas do grid (default: 11)")
    parser.add_argument("--row-spacing", type=float, default=25.0, help="Espaçamento entre linhas em metros (default: 25.0)")
    parser.add_argument("--col-spacing", type=float, default=18.0, help="Espaçamento entre pontos em metros (default: 18.0)")
    parser.add_argument("--speed", type=float, default=5.0, help="Velocidade de voo m/s (default: 5.0)")
    parser.add_argument("--alt", type=float, default=15.0, help="Altitude AGL em metros (default: 15.0)")
    parser.add_argument("--field-lat", type=float, default=DEFAULT_LAT, help="Latitude centro do talhão")
    parser.add_argument("--field-lon", type=float, default=DEFAULT_LON, help="Longitude centro do talhão")
    parser.add_argument("--stabilize-ms", type=int, default=DEFAULT_STABILIZE_MS, help="Tempo de estabilização ms (default: 500)")
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="Diretório base do dataset")
    parser.add_argument("--output-csv", default="scripts/output/missao_hil_georreferenciada.csv", help="Caminho do CSV de saída")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    simulator = HilMavlinkSimulator(args)
    asyncio.run(simulator.run_mission())
