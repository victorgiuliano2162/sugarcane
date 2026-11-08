#!/usr/bin/env python3
"""
Gerador de Mapas de Calor Georreferenciados e Camadas SIG (QGIS/GeoJSON/Leaflet).

Consome os logs georreferenciados gerados pela bancada HIL MAVLink
(scripts/output/missao_hil_georreferenciada.csv) e produz:
  1. Camada vetorial GeoJSON padrão RFC 7946 para QGIS, ArcGIS e Google Earth.
  2. Mapa interativo Web GIS (Leaflet / Folium) com satélite e filtros em camadas.
  3. Mapas de calor estáticos de alta resolução (PNG) com interpolação de densidade
     para Carvão (smut), Ferrugem Marrom (BrownRust) e severidade fitossanitária global.

Uso:
    python scripts/generate_infestation_heatmaps.py
    python scripts/generate_infestation_heatmaps.py --input scripts/output/missao_hil_georreferenciada.csv
"""

import sys
import os
import csv
import json
import math
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy.ndimage import gaussian_filter

try:
    import folium
    from folium.plugins import HeatMap, MeasureControl, Fullscreen
except ImportError:
    print("[ERRO] Biblioteca 'folium' não encontrada. Instale com: pip install folium")
    sys.exit(1)


CLASS_COLORS = {
    "Healthy Leaves": "#10b981",    # Verde esmeralda
    "Dried Leaves": "#64748b",      # Cinza azulado
    "Banded Chlorosis": "#facc15",  # Amarelo vibrante
    "Brown Spot": "#d97706",        # Âmbar/Laranja escuro
    "BrownRust": "#ea580c",         # Laranja avermelhado / Ferrugem
    "Grassy shoot": "#84cc16",      # Verde claro/amarelado
    "Pokkah Boeng": "#06b6d4",      # Ciano
    "Sett Rot": "#78350f",          # Marrom escuro
    "Viral Disease": "#8b5cf6",     # Roxo
    "Yellow Leaf": "#eab308",       # Amarelo foliar
    "smut": "#dc2626"               # Vermelho sangue (Carvão / Alta Severidade)
}


def load_csv(csv_path):
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["waypoint_id"] = int(row["waypoint_id"])
            row["row"] = int(row["row"])
            row["col"] = int(row["col"])
            row["lat"] = float(row["lat"])
            row["lon"] = float(row["lon"])
            row["alt_msl_m"] = float(row["alt_msl_m"])
            row["alt_agl_m"] = float(row["alt_agl_m"])
            row["confianca"] = float(row["confianca"])
            row["acerto"] = int(row["acerto"])
            row["severidade_risco"] = int(row["severidade_risco"])
            row["tempo_estabilizacao_ms"] = float(row["tempo_estabilizacao_ms"])
            row["tempo_decodificacao_ms"] = int(row["tempo_decodificacao_ms"])
            row["tempo_inferencia_ms"] = int(row["tempo_inferencia_ms"])
            row["tempo_total_pausa_ms"] = float(row["tempo_total_pausa_ms"])
            records.append(row)
    return records


def export_geojson(records, output_path):
    """
    Gera FeatureCollection GeoJSON em conformidade com RFC 7946 / EPSG:4326.
    Compatível com importação direta no QGIS, ArcGIS e Google Earth.
    """
    features = []
    for r in records:
        pred = r["classe_predita"]
        color = CLASS_COLORS.get(pred, "#3b82f6")
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lon"], r["lat"], r["alt_msl_m"]]
            },
            "properties": {
                "waypoint_id": r["waypoint_id"],
                "linha_talhao": r["row"],
                "coluna_talhao": r["col"],
                "classe_real": r["classe_real"],
                "classe_predita": pred,
                "confianca": r["confianca"],
                "confianca_pct": round(r["confianca"] * 100.0, 1),
                "acerto": bool(r["acerto"]),
                "severidade_risco": r["severidade_risco"],
                "tempo_decodificacao_ms": r["tempo_decodificacao_ms"],
                "tempo_inferencia_ms": r["tempo_inferencia_ms"],
                "tempo_total_pausa_ms": r["tempo_total_pausa_ms"],
                "arquivo_amostra": r["arquivo_imagem"],
                "cor_hex": color,
                "alerta_critico": pred in ("smut", "BrownRust")
            }
        }
        features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "name": "Levantamento_Fitossanitario_Canavial_HIL",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2, ensure_ascii=False)
    print(f"[GeoJSON] Camada SIG salva com sucesso em: {output_path}")


def generate_interactive_map(records, output_html_path):
    """
    Gera mapa interativo Folium / Leaflet completo com mosaico de satélite,
    grade de voo, marcadores coloridos e camadas de mapa de calor dinâmico.
    """
    if not records:
        return

    center_lat = sum(r["lat"] for r in records) / len(records)
    center_lon = sum(r["lon"] for r in records) / len(records)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=18,
        tiles=None
    )

    # Camadas Base
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite de Alta Resolução (Esri)",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap Padrão",
        overlay=False,
        control=True
    ).add_to(m)

    # 1. Delimitação do Talhão (Polígono com margem)
    min_lat = min(r["lat"] for r in records) - 0.00012
    max_lat = max(r["lat"] for r in records) + 0.00012
    min_lon = min(r["lon"] for r in records) - 0.00015
    max_lon = max(r["lon"] for r in records) + 0.00015

    talhao_coords = [
        [min_lat, min_lon],
        [min_lat, max_lon],
        [max_lat, max_lon],
        [max_lat, min_lon],
        [min_lat, min_lon]
    ]

    folium.Polygon(
        locations=talhao_coords,
        color="#34d399",
        weight=2,
        fill=True,
        fill_color="#10b981",
        fill_opacity=0.08,
        tooltip="<b>Talhão 04 - Canavial de Produção</b><br>Ribeirão Preto / SP"
    ).add_to(m)

    # 2. Trajetória de Voo (PolyLine)
    flight_line = [[r["lat"], r["lon"]] for r in records]
    folium.PolyLine(
        flight_line,
        color="#38bdf8",
        weight=2,
        opacity=0.6,
        dash_array="5, 8",
        tooltip="Trajetória de Voo VANT (Serpentina)"
    ).add_to(m)

    # 3. Grupo de Todos os Pontos Amostrais
    fg_all = folium.FeatureGroup(name="Pontos de Amostragem (Todos)", show=True)
    fg_smut = folium.FeatureGroup(name="Focos de Carvão (smut)", show=True)
    fg_rust = folium.FeatureGroup(name="Focos de Ferrugem (BrownRust)", show=True)

    for r in records:
        pred = r["classe_predita"]
        color = CLASS_COLORS.get(pred, "#3b82f6")
        is_smut = (pred == "smut")
        is_rust = (pred == "BrownRust")

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 12px; width: 240px; line-height: 1.4;">
            <div style="background: {color}; color: white; padding: 6px 10px; border-radius: 4px; font-weight: bold; margin-bottom: 6px;">
                Waypoint #{r['waypoint_id']} ({pred})
            </div>
            <b>Talhão:</b> Linha {r['row']}, Col {r['col']}<br>
            <b>Diagnóstico:</b> {pred}<br>
            <b>Confiança:</b> {r['confianca']*100:.1f}%<br>
            <b>Gabarito Real:</b> {r['classe_real']}<br>
            <b>Decodificação:</b> {r['tempo_decodificacao_ms']} ms<br>
            <b>Inferência ESP32:</b> {r['tempo_inferencia_ms']} ms<br>
            <b>Ciclo de Parada:</b> {r['tempo_total_pausa_ms']:.0f} ms<br>
            <b>Amostra:</b> <code>{r['arquivo_imagem']}</code>
        </div>
        """

        marker = folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=6 if not (is_smut or is_rust) else 8,
            color="#ffffff",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"WP #{r['waypoint_id']}: {pred} ({r['confianca']*100:.1f}%)"
        )
        marker.add_to(fg_all)

        if is_smut:
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=10,
                color="#dc2626",
                weight=3,
                fill=True,
                fill_color="#dc2626",
                fill_opacity=0.75,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"ALERTA CARVÃO: WP #{r['waypoint_id']}"
            ).add_to(fg_smut)

        if is_rust:
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=10,
                color="#ea580c",
                weight=3,
                fill=True,
                fill_color="#ea580c",
                fill_opacity=0.75,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"ALERTA FERRUGEM: WP #{r['waypoint_id']}"
            ).add_to(fg_rust)

    fg_all.add_to(m)
    fg_smut.add_to(m)
    fg_rust.add_to(m)

    # 4. Mapas de Calor (HeatMaps)
    # 4a. Heatmap Global de Severidade de Risco
    heat_data_global = [[r["lat"], r["lon"], r["severidade_risco"] + 0.2] for r in records]
    HeatMap(
        heat_data_global,
        name="Mapa de Calor: Severidade Global",
        min_opacity=0.25,
        radius=25,
        blur=18,
        max_zoom=1,
        gradient={0.2: "#3b82f6", 0.5: "#eab308", 0.8: "#ea580c", 1.0: "#dc2626"}
    ).add_to(m)

    # 4b. Heatmap Específico para Carvão (smut)
    heat_data_smut = [[r["lat"], r["lon"], 1.0 if r["classe_predita"] == "smut" else 0.0] for r in records]
    HeatMap(
        heat_data_smut,
        name="Mapa de Calor: Foco Carvão (smut)",
        min_opacity=0.3,
        radius=30,
        blur=20,
        gradient={0.3: "#f87171", 0.7: "#ef4444", 1.0: "#991b1b"}
    ).add_to(m)

    # 4c. Heatmap Específico para Ferrugem (BrownRust)
    heat_data_rust = [[r["lat"], r["lon"], 1.0 if r["classe_predita"] == "BrownRust" else 0.0] for r in records]
    HeatMap(
        heat_data_rust,
        name="Mapa de Calor: Foco Ferrugem (BrownRust)",
        min_opacity=0.3,
        radius=30,
        blur=20,
        gradient={0.3: "#fdba74", 0.7: "#f97316", 1.0: "#c2410c"}
    ).add_to(m)

    # Controles adicionais
    folium.LayerControl(collapsed=False).add_to(m)
    MeasureControl(position="topleft").add_to(m)
    Fullscreen().add_to(m)

    # Legenda Flutuante
    legend_html = """
    <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000; background: rgba(15, 23, 42, 0.92);
                color: #f1f5f9; padding: 14px 18px; border-radius: 8px; border: 1px solid #334155;
                font-family: Arial, sans-serif; font-size: 11px; box-shadow: 0 4px 16px rgba(0,0,0,0.4); max-width: 250px;">
        <b style="font-size: 12px; color: #34d399;">Diagnóstico Fitossanitário ESP32-S3</b><br>
        <span style="color: #94a3b8;">Classificação em Borda por Visão Computacional</span>
        <hr style="border: 0; border-top: 1px solid #334155; margin: 8px 0;">
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="background: #10b981; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <span>Saudável (Healthy)</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="background: #dc2626; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <b>Carvão (smut) - Crítico</b>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="background: #ea580c; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <b>Ferrugem (BrownRust) - Crítico</b>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="background: #eab308; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <span>Clorose / Folha Amarela</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="background: #64748b; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <span>Folhas Secas (Dried)</span>
        </div>
        <div style="display: flex; align-items: center;">
            <span style="background: #8b5cf6; width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
            <span>Outras Patologias</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    os.makedirs(os.path.dirname(output_html_path), exist_ok=True)
    m.save(output_html_path)
    print(f"[Leaflet] Mapa interativo Web GIS salvo em: {output_html_path}")


def generate_static_heatmaps(records, output_dir):
    """
    Gera mapas de calor estáticos em PNG de alta resolução com Matplotlib,
    mostrando a distribuição no talhão, superfície contínua interpolada e métricas.
    """
    os.makedirs(output_dir, exist_ok=True)

    rows = max(r["row"] for r in records) + 1
    cols = max(r["col"] for r in records) + 1

    # Cria matrizes de grid (rows x cols)
    severity_grid = np.zeros((rows, cols), dtype=np.float32)
    smut_grid = np.zeros((rows, cols), dtype=np.float32)
    rust_grid = np.zeros((rows, cols), dtype=np.float32)
    decode_ms_grid = np.zeros((rows, cols), dtype=np.float32)
    infer_ms_grid = np.zeros((rows, cols), dtype=np.float32)
    pause_ms_grid = np.zeros((rows, cols), dtype=np.float32)

    for r in records:
        rw = r["row"]
        cl = r["col"]
        pred = r["classe_predita"]
        severity_grid[rw, cl] = r["severidade_risco"]
        smut_grid[rw, cl] = 1.0 if pred == "smut" else 0.0
        rust_grid[rw, cl] = 1.0 if pred == "BrownRust" else 0.0
        decode_ms_grid[rw, cl] = r["tempo_decodificacao_ms"]
        infer_ms_grid[rw, cl] = r["tempo_inferencia_ms"]
        pause_ms_grid[rw, cl] = r["tempo_total_pausa_ms"]

    # Interpolação contínua (Gaussian Splatting / KDE 2D)
    severity_smooth = gaussian_filter(severity_grid, sigma=0.85, mode="nearest")
    smut_smooth = gaussian_filter(smut_grid, sigma=0.85, mode="nearest")
    rust_smooth = gaussian_filter(rust_grid, sigma=0.85, mode="nearest")

    # --------------------------------------------------------------------------
    # FIGURA 1: Painel Completo de Monitoramento Fitossanitário 2D
    # --------------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=200)
    plt.subplots_adjust(hspace=0.28, wspace=0.22)

    # (a) Mapa Espacial dos Pontos Amostrais no Talhão
    ax = axes[0, 0]
    ax.set_title("(a) Levantamento Fitossanitário Amostral (Talhão 04)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Distância Longitudinal (Pontos ao longo da linha)", fontsize=9)
    ax.set_ylabel("Linhas de Plantio (Passadas VANT)", fontsize=9)
    
    # Desenha linhas de voo conectando os pontos
    for i in range(len(records) - 1):
        r1, r2 = records[i], records[i+1]
        ax.plot([r1["col"], r2["col"]], [r1["row"], r2["row"]],
                color="#94a3b8", linestyle="--", linewidth=1.0, alpha=0.6, zorder=1)

    # Plota marcadores dos pontos
    for r in records:
        pred = r["classe_predita"]
        c = CLASS_COLORS.get(pred, "#3b82f6")
        sz = 140 if pred in ("smut", "BrownRust") else 90
        marker = "s" if pred in ("smut", "BrownRust") else "o"
        ax.scatter(r["col"], r["row"], c=c, s=sz, marker=marker, edgecolors="#1e293b", linewidth=1.2, zorder=2)
        ax.text(r["col"], r["row"], str(r["waypoint_id"]), fontsize=6.5, ha="center", va="center", color="white", fontweight="bold", zorder=3)

    ax.set_xticks(range(cols))
    ax.set_yticks(range(rows))
    ax.set_xticklabels([f"C{c}" for c in range(cols)], fontsize=8)
    ax.set_yticklabels([f"L{r}" for r in range(rows)], fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.set_facecolor("#f8fafc")

    # (b) Superfície Contínua de Risco Fitossanitário (Heatmap)
    ax = axes[0, 1]
    ax.set_title("(b) Mapa de Calor Contínuo: Índice de Severidade Patogênica", fontsize=11, fontweight="bold")
    im = ax.imshow(severity_smooth, cmap="YlOrRd", interpolation="bicubic", origin="lower", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Severidade Estimada (0 = Saudável, 2 = Epidêmico)", fontsize=8)
    ax.set_xticks(range(cols))
    ax.set_yticks(range(rows))
    ax.set_xticklabels([f"C{c}" for c in range(cols)], fontsize=8)
    ax.set_yticklabels([f"L{r}" for r in range(rows)], fontsize=8)
    ax.set_xlabel("Distância Longitudinal (Pontos)", fontsize=9)
    ax.set_ylabel("Linhas de Plantio", fontsize=9)

    # Destaca focos com caixas delimitadoras
    rect_smut = patches.Rectangle((6.5, 2.5), 4.2, 1.8, linewidth=1.8, edgecolor="#dc2626", facecolor="none", linestyle="--")
    ax.add_patch(rect_smut)
    ax.text(8.6, 4.4, "Foco Carvão", color="#dc2626", fontsize=8.5, fontweight="bold", ha="center")

    rect_rust = patches.Rectangle((6.5, -0.4), 4.2, 1.8, linewidth=1.8, edgecolor="#ea580c", facecolor="none", linestyle="--")
    ax.add_patch(rect_rust)
    ax.text(8.6, 1.5, "Foco Ferrugem", color="#ea580c", fontsize=8.5, fontweight="bold", ha="center")

    # (c) Perfil de Latência por Waypoint no Hardware Real ESP32-S3
    ax = axes[1, 0]
    ax.set_title("(c) Perfil de Latência de Parada e Processamento On-Chip (ms)", fontsize=11, fontweight="bold")
    wp_ids = [r["waypoint_id"] for r in records]
    dec_times = [r["tempo_decodificacao_ms"] for r in records]
    inf_times = [r["tempo_inferencia_ms"] for r in records]
    stab_times = [r["tempo_estabilizacao_ms"] for r in records]

    p1 = ax.bar(wp_ids, stab_times, label="Estabilização VANT (~500ms)", color="#94a3b8", alpha=0.85)
    p2 = ax.bar(wp_ids, dec_times, bottom=stab_times, label="Decodificação JPEG (~102ms)", color="#38bdf8", alpha=0.85)
    bottom_inf = [s + d for s, d in zip(stab_times, dec_times)]
    p3 = ax.bar(wp_ids, inf_times, bottom=bottom_inf, label="Inferência SIMD INT8 (~283ms)", color="#10b981", alpha=0.85)

    ax.axhline(y=1000, color="#f43f5e", linestyle=":", linewidth=1.2, label="Meta 1.000 ms")
    ax.set_xlabel("Número do Waypoint Amostral", fontsize=9)
    ax.set_ylabel("Tempo de Ciclo (ms)", fontsize=9)
    ax.legend(loc="upper right", fontsize=7.5, framealpha=0.9)
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.set_xlim(0, len(wp_ids) + 1)
    ax.set_facecolor("#f8fafc")

    # (d) Distribuição e Acurácia por Classe Diagnosticada
    ax = axes[1, 1]
    ax.set_title("(d) Frequência das Classes Diagnosticadas pelo ESP32-S3", fontsize=11, fontweight="bold")
    class_counts = {}
    for r in records:
        p = r["classe_predita"]
        class_counts[p] = class_counts.get(p, 0) + 1

    sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    labels = [k for k, v in sorted_classes]
    counts = [v for k, v in sorted_classes]
    bar_colors = [CLASS_COLORS.get(k, "#3b82f6") for k in labels]

    bars = ax.barh(labels, counts, color=bar_colors, edgecolor="#1e293b", linewidth=0.8)
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.3, bar.get_y() + bar.get_height()/2.0, f"{int(w)} ({w/len(records)*100:.1f}%)",
                va="center", fontsize=8, fontweight="bold", color="#1e293b")

    ax.set_xlabel("Quantidade de Amostras Identificadas", fontsize=9)
    ax.set_xlim(0, max(counts) + 4)
    ax.grid(True, linestyle=":", alpha=0.4, axis="x")
    ax.invert_yaxis()
    ax.set_facecolor("#f8fafc")

    out_panel = os.path.join(output_dir, "mapa_infestacao_talhao_2d.png")
    fig.savefig(out_panel, bbox_inches="tight")
    plt.close(fig)
    print(f"[Matplotlib] Painel geral 2D salvo em: {out_panel}")

    # --------------------------------------------------------------------------
    # FIGURA 2: Mapa de Calor Focado em Carvão (smut)
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6), dpi=200)
    ax.set_title("Detecção Fitossanitária de Foco de Carvão (Sporisorium scitamineum)\nTalhão 04 - Ribeirão Preto / SP (Co-Simulação HIL)",
                 fontsize=11, fontweight="bold", pad=12)
    im = ax.imshow(smut_smooth, cmap="Reds", interpolation="bicubic", origin="lower", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Probabilidade Local de Infestação de Carvão", fontsize=9)

    for r in records:
        if r["classe_predita"] == "smut":
            ax.scatter(r["col"], r["row"], c="#ffffff", edgecolors="#dc2626", s=130, marker="^", linewidth=2.0, zorder=3)
            ax.text(r["col"], r["row"] + 0.22, f"WP#{r['waypoint_id']}", color="#7f1d1d", fontsize=7.5, fontweight="bold", ha="center")

    ax.set_xticks(range(cols))
    ax.set_yticks(range(rows))
    ax.set_xticklabels([f"Coluna {c}" for c in range(cols)], fontsize=8)
    ax.set_yticklabels([f"Linha {r}" for r in range(rows)], fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.4, color="#fee2e2")

    out_smut = os.path.join(output_dir, "mapa_foco_carvao_smut.png")
    fig.savefig(out_smut, bbox_inches="tight")
    plt.close(fig)
    print(f"[Matplotlib] Mapa focado Carvão salvo em: {out_smut}")

    # --------------------------------------------------------------------------
    # FIGURA 3: Mapa de Calor Focado em Ferrugem Marrom (BrownRust)
    # --------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 6), dpi=200)
    ax.set_title("Detecção Fitossanitária de Foco de Ferrugem Marrom (Puccinia melanocephala)\nTalhão 04 - Ribeirão Preto / SP (Co-Simulação HIL)",
                 fontsize=11, fontweight="bold", pad=12)
    im = ax.imshow(rust_smooth, cmap="Oranges", interpolation="bicubic", origin="lower", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Probabilidade Local de Infestação de Ferrugem", fontsize=9)

    for r in records:
        if r["classe_predita"] == "BrownRust":
            ax.scatter(r["col"], r["row"], c="#ffffff", edgecolors="#ea580c", s=130, marker="D", linewidth=2.0, zorder=3)
            ax.text(r["col"], r["row"] + 0.22, f"WP#{r['waypoint_id']}", color="#7c2d12", fontsize=7.5, fontweight="bold", ha="center")

    ax.set_xticks(range(cols))
    ax.set_yticks(range(rows))
    ax.set_xticklabels([f"Coluna {c}" for c in range(cols)], fontsize=8)
    ax.set_yticklabels([f"Linha {r}" for r in range(rows)], fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.4, color="#ffedd5")

    out_rust = os.path.join(output_dir, "mapa_foco_ferrugem_brownrust.png")
    fig.savefig(out_rust, bbox_inches="tight")
    plt.close(fig)
    print(f"[Matplotlib] Mapa focado Ferrugem salvo em: {out_rust}")


def main():
    parser = argparse.ArgumentParser(description="Gerador de Mapas de Calor Georreferenciados para QGIS/SIG")
    parser.add_argument("--input", default="scripts/output/missao_hil_georreferenciada.csv",
                        help="Caminho do CSV de telemetria da missão HIL")
    parser.add_argument("--out-dir", default="scripts/output",
                        help="Pasta de saída para relatórios e mapas")
    args = parser.parse_args()

    records = load_csv(args.input)
    print(f"[Info] Carregados {len(records)} registros georreferenciados de {args.input}")

    # Salva nas pastas scripts/output/ e docs/heatmaps/
    for out_dir in [args.out_dir, "docs/heatmaps"]:
        geojson_path = os.path.join(out_dir, "infestacao_talhao.geojson")
        html_path = os.path.join(out_dir, "mapa_calor_interativo.html")
        export_geojson(records, geojson_path)
        generate_interactive_map(records, html_path)
        generate_static_heatmaps(records, out_dir)

    print("\n[SUCESSO] Processamento cartográfico concluído com sucesso!")


if __name__ == "__main__":
    main()
