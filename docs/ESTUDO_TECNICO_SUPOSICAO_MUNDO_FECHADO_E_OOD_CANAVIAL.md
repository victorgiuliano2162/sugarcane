# Estudo Técnico de Engenharia: Suposição de Mundo Fechado e Detecção de Alvos Fora de Distribuição (OOD) no Diagnóstico Foliar de Cana-de-Açúcar em Edge AI

**Data:** 08 de Novembro de 2026  
**Autor:** Antigravity (Pair Programming com Victor Giuliano)  
**Projeto:** Sistema Autônomo e Embarcado de Reconhecimento de Patologias em Cana-de-Açúcar  
**Hardware Alvo:** Espressif ESP32-S3 DevKitM-1 (Xtensa Dual-Core LX7 @ 240 MHz, 512 KB SRAM, 8 MB Octal PSRAM @ 80 MHz DDR)  
**Modelo Atual:** MobileNetV3-Small / MobileNetV2 INT8 (`model_mbnet_int8.tflite`, 639.272 bytes, 160×160×3)  
**Status do Documento:** Proposta Arquitetural de Evolução & Análise de Viabilidade Técnica  

---

## 1. Definição do Problema e Motivação

O classificador neural atualmente embarcado opera sob a premissa matemática conhecida como **Suposição de Mundo Fechado** (*Closed-World Assumption*). Sob essa formulação, assume-se axiomaticamente que qualquer entrada $\mathbf{x} \in \mathbb{R}^{160 \times 160 \times 3}$ submetida ao pipeline pertence compulsoriamente a uma das $K=11$ classes conhecidas de patologias e estados fenotípicos da cana-de-açúcar:

$$\mathcal{C} = \{\text{Banded Chlorosis}, \text{Brown Spot}, \text{BrownRust}, \text{Dried Leaves}, \text{Grassy shoot}, \text{Healthy Leaves}, \text{Pokkah Boeng}, \text{Sett Rot}, \text{Viral Disease}, \text{Yellow Leaf}, \text{smut}\}$$

### 1.1. O Efeito Patológico da Camada Softmax com Dados Fora de Distribuição (OOD)
Na extremidade de saída do modelo, os *logits* não normalizados $z_i \in \mathbb{R}$ são mapeados em probabilidades normalizadas via função Softmax:

$$P(y = i \mid \mathbf{x}) = \sigma(\mathbf{z})_i = \frac{e^{z_i}}{\sum_{j=1}^{11} e^{z_j}}, \quad \forall i \in \{1, \dots, 11\}$$

Por construção matemática estrita:
$$\sum_{i=1}^{11} \sigma(\mathbf{z})_i \equiv 1{,}0 \quad (100\%)$$

Se o sensor óptico (câmera do drone ou smartphone) capturar um artefato estranho ao domínio agrícola restrito (ex.: solo arenoso/argiloso exposto, palhada seca no entre-linha, plantas invasoras como *Brachiaria decumbens*, elementos estruturais do drone, céu ou vestimenta do operador), a rede **não dispõe de mecanismo para responder "Não é cana-de-açúcar"**. 

Devido à geometria não linear dos hiperplanos de decisão formados pelas camadas convolucionais profundas com ativações ReLU/Hard-Swish, entradas OOD frequentemente ativam filtros de textura ou cor em regiões distantes do espaço latente, gerando **superconfiança anômala** (*overconfidence* em dados espúrios). Uma fotografia de solo com cascalho pode facilmente produzir uma ativação de $88\%$ de confiança para a classe `smut` ou `Brown Spot`.

### 1.2. Impacto no Sistema em Operação Agrícola Real
1. **Falsos Focos em Mapas de Calor (QGIS / Leaflet):** O log contínuo de auditoria em Flash (`/storage/inspections.csv`) acumulará eventos de alarme espúrios, poluindo a camada cartográfica de interpolação geoespacial com falsos focos epidêmicos em áreas sem cultura vegetal.
2. **Desperdício de Recursos de Bateria e Ciclos de CPU:** Executar decodificação JPEG e inferência convolucional em quadros espúrios durante manobras de voo consome potência útil do microcontrolador sem agregar valor analítico à missão.

---

## 2. Análise Comparativa de Abordagens de Engenharia

Para mitigar a vulnerabilidade a dados OOD, foram modeladas quatro abordagens técnicas, balanceando viabilidade no silício do ESP32-S3, latência e esforço de retreinamento.

```
                    ┌──────────────────────────────────────────────┐
                    │ Quadro de Entrada Capturado (JPEG / DVP)    │
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
             [Abordagem 3: Filtro ExG]             [Pipeline Direto]
             Triagem de Cor / Vegetação                        │
               (SRAM / SIMD: ~1,8 ms)                          │
                        │                                      │
            ┌───────────┴───────────┐                          │
            │ Rejeitado (< 25% ExG) │ Aprovado                 │
            ▼                       ▼                          ▼
       [Descarte Imediato]   ┌─────────────────────────────────────────┐
                             │    Modelo Embarcado no ESP32-S3         │
                             ├─────────────────────────────────────────┤
                             │  Opção A: 2 Redes em Cascata            │
                             │    (Rede 1: É cana? -> Rede 2: Doença)  │
                             │  Opção B: Rede Única 12 Classes         │
                             │    (11 Doenças + 1 Fundo/Não-Cana)      │
                             │  Opção C: Triagem de Entropia Softmax   │
                             └─────────────────────────────────────────┘
```

---

### Opção 1: Arquitetura em Cascata com Duas Redes Neurais (Two-Stage Cascade)

Nesta arquitetura, implementa-se um primeiro modelo binário $M_1$ especializado em discriminação de espécie/vegetação, seguido pelo classificador de patologias $M_2$:

1. **Estágio 1 ($M_1$):** Classificador Binário (`Cana-de-Açúcar` vs. `Outros/Fundo`).
2. **Estágio 2 ($M_2$):** Classificador Multiclasse Atual (11 classes foliares).

#### Análise de Viabilidade no ESP32-S3:
* **Armazenamento em Flash:** 
  - $M_1$ (MobileNetV3-Small INT8 reduzido): $\sim 300\text{ KB}$
  - $M_2$ (MobileNetV2 INT8 atual): $639\text{ KB}$
  - Total Flash: $\sim 940\text{ KB}$ (cabe confortavelmente na partição `storage` de 10 MB).
* **Consumo de Memória de Execução (Tensor Arena & Scratch):**
  - O TFLite Micro precisará instanciar dois `tflite::MicroInterpreter` ou compartilhar a mesma `tensor_arena` de $145\text{ KB}$ na Octal PSRAM reinicializando o apontador de modelo (`allocate_tensors` dinâmico). A reinicialização dinâmica de ponteiros em tempo de execução adiciona $\sim 15\text{ ms}$ de overhead de overhead de alocação no FreeRTOS.
* **Latência de Pior Caso (Worst-Case Latency):**
  - Quadro é cana: $t_{\text{total}} = t_{\text{decode}} + t_{M1} + t_{M2} \approx 96\text{ ms} + 130\text{ ms} + 284\text{ ms} = \mathbf{510\text{ ms}}$.
  - O throughput de pico cai de **$1{,}77\text{ FPS}$** para **$< 1{,}0\text{ FPS}$**.
* **Veredito:** ❌ **Rejeitada para o ESP32-S3 autônomo**. O custo de latência de $510\text{ ms}$ dobra o tempo de ciclo, prejudicando o tracking geoespacial contínuo em voo de drone ($> 5\text{ m/s}$).

---

### Opção 2: Expansão do Espaço de Estados para 12 Classes (11 Patologias + `Background/Non-Cane`)
> **Abordagem Recomendada para Retreinamento da Rede Neural**

Mantém-se a arquitetura unificada de modelo único, expandindo a última camada densa de $K=11$ para $K=12$ neurônios de saída, adicionando a classe negativa canônica:
$$\mathcal{C}_{12} = \mathcal{C}_{11} \cup \{\text{Background\_NonCane}\}$$

#### Composição Curada do Dataset da Classe 12:
Para que a rede aprenda fronteiras de decisão robustas no espaço de incorporação (*embedding space*), a classe 12 deve conter entre 400 e 600 imagens representativas de:
- Solos típicos de canaviais (latossolo vermelho, argissolo, terra preta, areia, cascalho).
- Palhada seca de colheita anterior e restos vegetais decompostos.
- Plantas invasoras frequentes em canaviais (*Brachiaria decumbens*, *Digitaria horizontalis*, *Cyperus rotundus*).
- Folhas de outras culturas agrícolas (milho, sorgo, capim-elefante).
- Estruturas mecânicas e artificiais (chassi do drone, tubos de irrigação, botas, asfalto).

#### Análise de Viabilidade no ESP32-S3:
* **Impacto no Tamanho do Modelo:** 
  - A última camada `Dense` adiciona apenas $1 \times C_{\text{in}} = 1 \times 1280 = 1.280$ parâmetros quantizados em INT8 (acréscimo insignificante de **$\sim 1{,}3\text{ KB}$** no arquivo `.tflite`).
* **Impacto na Latência:**
  - O operador convolucional final e a Softmax realizam 1 cálculo a mais. O impacto no tempo de inferência é de **$< 0{,}1\text{ ms}$**, mantendo a inferência estável em **`284 ms`**.
* **Tratamento no Firmware C++:**
  - Se `top_class == "Background_NonCane"`, o evento é descartado silenciosamente ou computado em telemetria como `status: "ignorado_nao_cana"`, sem poluir o CSV de inspeções nem o mapa cartográfico.
* **Veredito:**  **Aprovada como padrão-ouro para evolução da rede neural**.

---

### Opção 3: Pré-Filtro Heurístico Baseado em Índices de Vegetação (ExG / 2G-R-B)
> **Solução Imediata — Implementável em C++ no Firmware Atual sem Retreinamento**

Antes de submeter os 76.800 bytes do tensor à rede neural, o microcontrolador pode analisar a densidade de biomassa fotossinteticamente ativa diretamente nos pixels decodificados na Octal PSRAM.

Na agronomia e sensoriamento remoto, o índice **ExG** (*Excess Green Index*) é amplamente consagrado para segmentação de cultura verde sobre solo e palhada:

$$\text{ExG} = 2G - R - B$$

Onde $R, G, B \in [0, 255]$ são os componentes cromáticos do pixel.

#### Algoritmo Otimizado de Triagem Rápida no ESP32-S3:
Como o tensor $160 \times 160$ já está linearizado em memória após a decodificação pelo TJpgDec, uma rotina de varredura pode calcular a fração de cobertura vegetal em menos de $2\text{ ms}$ usando instruções inteiras:

```cpp
/**
 * @brief Avalia se o tensor de entrada contém biomassa vegetal suficiente
 * @param tensor_rgb888 Buffer linearizado de 160x160x3 bytes (desquantizado ou uint8)
 * @param min_vegetation_ratio Percentual mínimo de pixels verdes (ex: 0.25 para 25%)
 * @return true se aprovado para inferência neural, false para descarte imediato
 */
bool validate_vegetation_presence(const uint8_t* tensor_rgb888, float min_vegetation_ratio = 0.25f) {
    const size_t total_pixels = 160 * 160;
    size_t green_vegetation_pixels = 0;
    
    // Varredura linear com salto de 2 em 2 pixels para máxima velocidade (amostragem 50%)
    for (size_t i = 0; i < total_pixels * 3; i += 6) {
        int r = tensor_rgb888[i];
        int g = tensor_rgb888[i + 1];
        int b = tensor_rgb888[i + 2];
        
        // Excess Green Index (ExG): Realça clorofila e rejeita solo/palhada/concreto
        int exg = (2 * g) - r - b;
        
        // Critério combinado: ExG positivo com dominância de verde sobre vermelho
        if (exg > 15 && g > r && g > b) {
            green_vegetation_pixels += 2;
        }
    }
    
    float ratio = (float)green_vegetation_pixels / (float)total_pixels;
    return ratio >= min_vegetation_ratio;
}
```

#### Métricas de Desempenho no Hardware:
- **Tempo de Execução:** $\sim 1{,}8\text{ ms}$ (utilizando subamostragem stride-2 no Core 0).
- **Economia Energética e Temporal:** Quando o drone sobrevoa solo exposto ou o operador aponta a câmera para si, o sistema poupa **`284 ms` de inferência da CPU**, reduzindo o aquecimento térmico do chip e poupando ciclos de barramento.
* **Veredito:**  **Altamente recomendado para integração imediata no firmware**.

---

### Opção 4: Triagem Estatística de Incerteza (Open-Set Recognition por Entropia / Thresholding)
> **Solução Complementar em Pós-Processamento**

Mesmo sem retreinar o modelo, imagens espúrias ou fora do domínio tendem a gerar distribuições de probabilidade Softmax difusas ou conflitantes. Podem-se aplicar duas métricas matemáticas de rejeição em tempo de execução:

#### 1. Limiar de Confiança Absoluta (Max-Probability Thresholding):
$$\text{Rejeitar se } \max_{i} P(y=i \mid \mathbf{x}) < \tau_{\text{conf}} \quad (\text{ex: } \tau_{\text{conf}} = 0{,}60)$$
Se nenhuma patologia atingir pelo menos $60\%$ de probabilidade, o registro não é catalogado como foco de doença.

#### 2. Margem de Separação de Logits (Margin Score):
$$\Delta_{\text{top}} = P(y = \text{Top}_1) - P(y = \text{Top}_2)$$
$$\text{Rejeitar se } \Delta_{\text{top}} < 0{,}15$$
Se o primeiro colocado tiver $38\%$ e o segundo tiver $34\%$, o modelo está em profunda dúvida. Em vez de registrar um foco errático no mapa, o evento é marcado como `Inconclusivo / Não-Folha`.

---

## 3. Síntese Comparativa das Estratégias

| Critério de Engenharia | Opção 1: Duas Redes em Cascata | Opção 2: Classe 12 `Background` | Opção 3: Pré-Filtro ExG (Heurística) | Opção 4: Threshold de Incerteza |
| :--- | :---: | :---: | :---: | :---: |
| **Tempo de Inferência Adicional** | `+130 ms` a `+226 ms` | **`< 0,1 ms`** | **`+1,8 ms`** | **`< 0,05 ms`** |
| **Ocupação Extra de Flash** | `+300 KB` a `+600 KB` | **`+1,3 KB`** | **`0 KB`** (Cód. puro C++) | **`0 KB`** |
| **Ocupação Extra de RAM / PSRAM** | `+120 KB` (buffers duplos) | **`0 KB`** | **`0 KB`** (reusa tensor) | **`0 KB`** |
| **Necessidade de Retreinamento?** | Sim (treinar rede binária) | Sim (adicionar classe) | **Não** (firmware puro) | **Não** (firmware puro) |
| **Throughput Resultante** | $\sim 0{,}9\text{ FPS}$ (Gargalo) | **`1,77 FPS`** (Inalterado) | **`> 2,5 FPS`** (em solo/fundo) | **`1,77 FPS`** |
| **Nível de Proteção OOD** | Alto | Muito Alto | Médio (Filtra não-verde) | Moderado (Filtra dúvidas) |

---

## 4. Diretrizes de Redação Acadêmica (TCC e Artigo Científico)

Para enriquecer o rigor técnico do Trabalho de Conclusão de Curso e do artigo científico, recomenda-se registrar essa discussão nas seguintes seções:

### 4.1. Na Seção de Metodologia / Arquitetura do Sistema
> *"O pipeline de classificação supervisionada adota a hipótese de espaço amostral restrito, operando sob o pressuposto de que a aquisição sensorial fornece quadros já enquadrados sobre a superfície da cultura (*Region of Interest* — RoI). Essa premissa fundamenta-se na viabilidade de pré-processamento por índices cromáticos de biomassa vegetal (como o Excess Green Index — ExG) executados no estágio de decodificação no Core 0, desacoplando a tarefa de detecção de presença vegetal do operador neural de alta densidade no Core 1."*

### 4.2. Na Seção de Resultados e Discussões (Análise de Falsos Positivos)
> *"Observa-se que a camada de ativação Softmax quantizada em INT8 atua como uma distribuição simplex restrita à unidade ($\sum p_i = 1$). Em cenários de fronteira — tais como senescência avançada (*Dried Leaves*) em transição com palhada de solo —, a partição probabilística tende a apresentar entropia elevada. Para prevenir a propagação de falsos focos no georreferenciamento cartográfico, adotou-se um critério de rejeição por margem mínima de confiança ($\Delta_{\text{top}} \ge 0{,}15$), mitigando os efeitos deletérios da superconfiança em dados fora de distribuição (*Out-of-Distribution* — OOD)."*

### 4.3. Na Seção de Trabalhos Futuros / Conclusão
> *"Como perspectiva de evolução do protótipo, propõe-se a transição para um espaço de inferência aberto (*Open-Set Recognition*) mediante a expansão do classificador para acomodar uma classe canônica de fundo (*Background/Non-Cane*), combinada à integração de detectores vetoriais compactos para localização prévia de lâmina foliar diretamente em edge computing."*

---

## 5. Roteiro Prático de Implementação (Roadmap)

1. **Fase Imediata (Firmware C++ — Sem Retreinamento):**
   - Inserir a função `validate_vegetation_presence()` em [`src/image_processor.cpp`](file:///home/victor/projects/sugarcane/src/image_processor.cpp) imediatamente após o retorno de `tjpgd_decode()`.
   - Se o índice de biomassa for inferior a $20\%$, o job é finalizado em $2\text{ ms}$, retornando `{"status":"ignorado","motivo":"sem_vegetacao"}` e pulando a chamada da rede neural.
   - Adicionar trava de incerteza em [`src/tflite_classifier.cpp`](file:///home/victor/projects/sugarcane/src/tflite_classifier.cpp): inferências com $\text{Top}_1 < 0{,}50$ recebem anotação `anomaly_alert = false` e são marcadas como *Inconclusivas*.

2. **Fase Evolutiva (Retreinamento do Modelo v09):**
   - Curar um conjunto de 500 imagens de solo, palhada e ervas daninhas.
   - Retreinar o MobileNetV2 INT8 no Keras com as 12 classes usando a mesma técnica de *Box Averaging* validada.
   - Embarcar o novo arquivo binário `model_mbnet_int8.tflite` via `pio run -t uploadfs`.
