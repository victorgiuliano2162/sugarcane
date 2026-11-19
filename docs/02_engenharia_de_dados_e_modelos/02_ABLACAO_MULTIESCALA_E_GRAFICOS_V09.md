# Guia de Interpretação dos Gráficos Analíticos — Notebook v09
**Projeto:** Diagnóstico Fitopatológico em Cana-de-Açúcar no ESP32-S3 (TinyML & Edge AI)  
**Notebook de Referência:** [notebooks/cane_disease_esp32s3_v09.ipynb](file:///home/victor/projects/sugarcane/notebooks/cane_disease_esp32s3_v09.ipynb)  
**Arquiteturas Avaliadas:** MobileNetV2 com $\alpha \in \{0.35, 0.50, 0.75\}$ sob Quantization-Aware Training (QAT Int8).

---

## 1. Visão Geral da Abordagem Visual na Versão v09

A versão `v09` abandonou o modelo sequencial customizado (devido à ineficiência de convoluções densas frente ao conjunto de instruções vetoriais SIMD `esp-nn` do ESP32-S3) e focou em uma **análise de ablação em multi-escala da MobileNetV2**.

Como redes com $\alpha=0.50$ (~700k parâmetros) e $\alpha=0.75$ (~1,38M parâmetros) possuem capacidade significativamente maior que a $\alpha=0.35$ (~410k parâmetros) para um dataset de 4.313 imagens de treino, cada gráfico foi desenhado para responder a uma pergunta técnica fundamental de **ciência de dados** e **co-design de engenharia de hardware**.

---

## 2. Detalhamento e Interpretação Gráfico por Gráfico

### Gráfico 1: Dinâmica de Convergência e Controle de Overfitting (Grid 3x2)
* **Estrutura:** 3 linhas (uma para cada escala: $\alpha=0.35$, $\alpha=0.50$, $\alpha=0.75$) e 2 colunas (Acurácia à esquerda, Focal Loss à direita).
* **O que analisa:**
  1. A transição contínua entre as **três fases de treino**:
     - *Fase 1 (Head Warmup):* Treino exclusivo do classificador denso com base congelada.
     - *Fase 2 (Fine-Tuning Seletivo):* Descongelamento parcial do backbone com camadas de `BatchNormalization` congeladas e *Gradient Clipping*.
     - *Fase 3 (QAT Int8):* Calibração de pesos e ativações com nós *FakeQuant* de 8 bits.
  2. A evolução do **Generalization Gap** (diferença entre as curvas de Treino e Validação, realçada pela área sombreada colorida).
* **Como interpretar:**
  - **Transições de Fase (Linhas Verticais):** A linha tracejada roxa marca a entrada no *Fine-Tuning*; a linha tracejada vermelha marca o início do QAT. No QAT, é esperado ver uma oscilação na Época 1 (pela inserção dos nós de quantização) seguida de rápida estabilização.
  - **Controle de Overfitting:** Se a curva de treino subir para >99% enquanto a validação estagnar ou cair, há sobreajuste (memorização). O sucesso das estratégias da v09 (ruído de sensor, Dropout escalonado de 0.30 a 0.50, MixUp e congelamento seletivo de 25% a 45% do backbone) é comprovado quando a área sombreada se mantém **estreita ($\le 5\text{--}8\%$)**, mesmo em $\alpha=0.75$.
  - **Comportamento da Loss:** A Focal Loss ($\gamma=2.0$) de validação deve convergir de forma suave. Se ela começar a divergir enquanto a acurácia se mantém, indica que a rede está ficando calibrada com menor confiança, o que é contido pelo *Label Smoothing*.

---

### Gráfico 2: Matrizes de Confusão Normalizadas (Grid 2x3)
* **Estrutura:** 2 linhas (Float32 no topo, Int8 QAT na base) $\times$ 3 colunas ($\alpha=0.35$, $\alpha=0.50$, $\alpha=0.75$).
* **O que analisa:**
  - A taxa de acerto por classe real (**Sensibilidade / Recall %**) na diagonal principal.
  - As confusões cruzadas específicas entre patologias foliares com sintomas visuais similares (ex.: *Pokkah Boeng* vs. *smut*, *BrownRust* vs. *Banded Chlorosis*).
  - O impacto da quantização Int8 nos erros de classificação (comparando a linha superior com a inferior).
* **Como interpretar:**
  - **Diagonal Principal:** Quanto mais próximo de **100%** (tons escuros), melhor a capacidade do modelo de reconhecer aquela doença específica.
  - **Células Fora da Diagonal:** Revelam confusões botânicas. Por exemplo, se houver confusão entre *Yellow Leaf* e folhas sadias (*Healthy*), isso reflete sintomas iniciais de clorose foliar.
  - **Fidelidade da Quantização ($\Delta$):** Ao comparar cada coluna verticalmente (Float32 vs. Int8), a matriz Int8 deve apresentar distribuição idêntica ou com variação mínima ($\pm 1\text{--}2\%$), validando a eficácia do QAT em relação a quantizações pós-treino (PTQ) convencionais que colapsam classes minoritárias.

---

### Gráfico 3: Desempenho por Patologia e Indicadores Globais vs. Meta SOTA (Barras Agrupadas)
* **Estrutura:** Barras agrupadas para cada uma das 9 classes e para as métricas agregadas (*Top-1*, *Top-2*, *F1-Macro*, *Kappa $\kappa$*), comparando $\alpha=0.35$ (verde), $\alpha=0.50$ (azul) e $\alpha=0.75$ (roxo).
* **O que analisa:**
  - Se o aumento da capacidade da rede ($\alpha$) traz ganho homogêneo entre todas as patologias ou se beneficia principalmente classes complexas e minoritárias.
  - Conformidade com a **Linha de Referência de 90%** (limiar aceito para sistemas autônomos de triagem agrícola em campo).
* **Como interpretar:**
  - **Sensibilidade a Classes Difíceis:** Observe as barras de *smut* (carvão) e *Yellow Leaf*. Redes com $\alpha=0.50$ e $0.75$ tendem a capturar nuances morfológicas que redes ultra-leves ($\alpha=0.35$) por vezes simplificam.
  - **Top-2 Accuracy:** Frequentemente atinge **$>97\text{--}98\%$**. Em inspeção com drone em voo pairado, a probabilidade Top-2 serve como gatilho de segurança operacional: se a primeira hipótese tiver confiança moderada, o sistema notifica o agrônomo com as duas patologias prováveis.
  - **Kappa de Cohen ($\kappa$) e F1-Macro:** Ambas devem se manter acima de **$90\%$**, comprovando que a acurácia global não está inflada por classes com maior volume de amostras.

---

### Gráfico 4: Dashboard de Co-Design Hardware/Software no ESP32-S3 (2x2 Subplots)
Este é o painel central de validação de engenharia embarcada, integrando restrições de silício com métricas computacionais.

* **Subplot 4A — Fronteira de Pareto (Latência ESP32-S3 ms vs. Acurácia Top-1 Int8 %):**
  - *Área das bolhas:* Proporcional ao tamanho do binário `.tflite` em Flash.
  - *Zonas de Operação de Voo:*
    - **Verde (< 350 ms):** Zona de tempo real estrito para inspeção contínua (permite $>2,8$ inferências por segundo).
    - **Amarela (350–650 ms):** Zona operacional viável para voo pairado ou disparo sob demanda.
    - **Vermelha (> 650 ms):** Risco de desestabilização da missão ou atraso excessivo na telemetria.
  - *Interpretação:* Mostra se o ganho de acurácia de $\alpha=0.50$ ou $0.75$ justifica pagar o dobro ou o quádruplo do tempo de inferência e gasto de bateria.

* **Subplot 4B — Ocupação da Hierarquia de Memória do ESP32-S3 (% do Limite Físico):**
  - *O que compara:* 3 recursos de hardware cruciais:
    1. **Scratch Buffer SIMD `esp-nn`:** Buffer em SRAM interna de baixa latência (limite estrito de **48 KB**).
    2. **Tensor Arena:** Memória de ativação ping-pong em PSRAM Octal (orçamento alocado de **800 KB**).
    3. **Flash LittleFS:** Partição `/models` na memória Flash SPI (orçamento de **1.536 KB** / 1,5 MB).
  - *Interpretação:* Nenhuma barra pode ultrapassar a linha vermelha de **100%**. Em especial, note que o modelo $\alpha=0.75$ consome quase a totalidade da partição de 1,5 MB, enquanto $\alpha=0.35$ consome apenas ~40%.

* **Subplot 4C — Fidelidade de Quantização, Top-2 e NetScore ($\Omega$ em dB):**
  - *O que compara:* Top-1 Float32 vs. Top-1 Int8 vs. Top-2 Int8 no eixo primário, e a curva de eficiência de rede **NetScore ($\Omega$)** de Wong (2019) no eixo secundário:
    $$\Omega = 20 \cdot \log_{10}\left(\frac{\text{Acc}(\%)^2}{\text{Params(M)}^{0.5} \cdot \text{MACs(M)}^{0.5}}\right)$$
  - *Interpretação:* Ilustra a lei dos rendimentos decrescentes. Modelos maiores apresentam ligeiro incremento de acurácia, mas sofrem uma queda expressiva no NetScore devido ao crescimento quadrático no número de operações.

* **Subplot 4D — Calibração Probabilística Int8 (Confiança em Acertos vs. Erros e ECE %):**
  - *O que analisa:* Se as probabilidades de saída do *Softmax* quantizado refletem a certeza real do modelo.
  - *Interpretação:*
    - A confiança média nas classificações **corretas** deve ser alta ($>85\text{--}90\%$).
    - A confiança média nas predições **incorretas** deve ser baixa ($<55\text{--}65\%$), permitindo rejeitar predições duvidosas por limiar de corte no firmware C++.
    - O **Expected Calibration Error (ECE %)** deve ser o menor possível ($\le 5\text{--}7\%$).

---

### Gráfico 5: Posicionamento frente ao Estado da Arte (Literatura SOTA vs. TinyML)
* **Estrutura:** Dispersão bidimensional com o Tamanho do Modelo em Megabytes (escala logarítmica de 0,1 MB a 1.000 MB no eixo horizontal) versus Acurácia Global Top-1 (%) no eixo vertical.
* **O que analisa:**
  - Confronta os modelos `v09` e o benchmark físico de 6.748 imagens no ESP32-S3 contra arquiteturas clássicas da literatura fitopatológica de cana-de-açúcar (VGG-16, ResNet-50, DenseNet-121, MobileNetV2-1.0 em precisão Float32).
  - Delimita a **Zona Viável de Flash do ESP32-S3 ($\le 1,5\text{ MB}$)** com preenchimento verde.
* **Como interpretar:**
  - Demonstra que modelos da literatura acadêmica padrão (como VGG-16 com 528 MB ou ResNet-50 com 94 MB) são fisicamente inviáveis para microcontroladores sem sistema operacional, exigindo servidores ou GPUs de alto custo.
  - Os modelos desenvolvidos situam-se no quadrante superior esquerdo ótimo: **tamanho de 0,6 a 1,9 MB (redução de até 800x)** mantendo acurácia compatível ou superior (**92% a 94%**) com os trabalhos de referência.

---

### Gráfico 6: Radar Multidimensional de Co-Design Embarcado (Spider Chart de 6 Eixos)
* **Estrutura:** Gráfico polar com 6 eixos normalizados em índice de mérito [0 a 100]:
  1. *Acurácia Top-1 (Int8)*
  2. *F1-Macro (Equilíbrio entre classes)*
  3. *Velocidade FPS (Rendimento no ESP32-S3)*
  4. *Economia de Flash (Margem livre no LittleFS)*
  5. *Margem de SRAM (Folga nos 48 KB da `esp-nn`)*
  6. *Eficiência NetScore ($\Omega$)*
* **O que analisa:**
  - Sintetiza o perfil global de cada arquitetura em uma única assinatura geométrica.
* **Como interpretar:**
  - **MobileNetV2 $\alpha=0.35$ (Verde):** Apresenta área expandida para os eixos de hardware (alta pontuação em FPS, economia de Flash, folga de SRAM e NetScore), com acurácia competitiva ($>92\%$). É o modelo de escolha para operação contínua e restrição severa de consumo.
  - **MobileNetV2 $\alpha=0.50$ (Azul):** Perfil equilibrado, oferecendo um meio-termo para aplicações onde 500 ms de inferência são toleráveis e deseja-se maximizar a sensibilidade em classes difíceis.
  - **MobileNetV2 $\alpha=0.75$ (Roxo):** Perfil com viés puramente preditivo (ápice em Acurácia e F1), porém retraído nos eixos de recursos físicos (opera próximo dos limites de tempo e armazenamento do microcontrolador).

---

## 3. Resumo das Decisões para Apresentação no TCC

1. **Justificativa para descontinuar a CNN Customizada:** Os gráficos 4 e 5 comprovam que convoluções densas consom mais Flash e RAM sem usufruir da aceleração vetorial SIMD para *depthwise separable convolutions* da biblioteca `esp-nn`.
2. **Definição do Modelo Padrão no Firmware:** A Fronteira de Pareto (Gráfico 4A) e o Radar (Gráfico 6) respaldam formalmente a escolha da **MobileNetV2 $\alpha=0.35$** como modelo embarcado de produção, reservando $\alpha=0.50$ como alternativa para bancada ou inspeção estática.
3. **Validação da Metodologia:** O estreitamento do *gap* no Gráfico 1 e os baixos valores de ECE no Gráfico 4D atestam que as medidas de regularização adaptativa controlaram com eficácia o sobreajuste em redes mais largas.
