# Módulo Biblioteca — o hub read-only (a categoria estrutural oposta)

Delta doc. A Biblioteca fecha a Sessão 4 ensinando a **categoria estrutural oposta** a tudo que vimos:
um **hub read-only, sem worker nem pipeline**. Se as ferramentas transformam entrada→saída, a
Biblioteca só **navega e abre** o que já existe sob `output/`.

> **Base:** [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md) (o contraste: aqui **não** há
> pipeline), [`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §3 (thread + repintura escopada),
> [`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) (mapa/tags/dedup).

## A grande diferença — sem worker, sem pipeline

🔑 Todos os módulos-ferramenta têm `worker.py`, `run_queue_pipeline`, contrato de eventos. A Biblioteca
**não tem nada disso**: é **read-only**. As ações não disparam um pipeline — disparam **navegação** ou
**abertura de arquivo**. É a prova de que "módulo" no projeto não significa "processa dados": significa
"uma entrada no `MODULES` com um `control`" ([`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §4.3).
A Biblioteca é um hub (botão dourado no AppBar), não uma ferramenta na rail.

## Novidade 1 — o scanner de `output/`

`core/library/scanner.py` varre cada diretório de saída e o mapeia para `(kind, category)` — incluindo
`transcription/subtitles`. É como o hub "sabe" o que você já produziu, sem estado próprio: ele **lê o
disco** a cada visita. Fonte única de caminhos (as constantes do [`../arquivos/utils.md`](../arquivos/utils.md))
paga dividendo aqui — o scanner sabe onde varrer porque todo módulo grava no dir canônico.

## Novidade 2 — thumbnails numa thread, com repintura **escopada**

`thumbnails.py` gera miniaturas: despacha primeiro por **sufixo de imagem** (qualquer kind — cobre o
PNG de waveform/espectrograma do Áudio), depois por kind (document/video). Para PDF, **reusa** o
`render_first_page_png` do Documentos ([`documentos.md`](documentos.md) §3). As miniaturas são geradas
numa **thread daemon** com update **escopado** — 🔑 nunca `page.update()` global (que quebraria uma
animação e é caro), sempre `controle.update()` no item ([`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md)
§3.1). É o mesmo cuidado de repintura da regra do spinner, agora sem pipeline.

## Novidade 3 — 4 modos de visão + ações que navegam

A GUI tem 4 modos (Grade·Lista·**Painel**·**Mapa**), com filtro/busca/categoria. As ações:

- **Abrir** — texto vai para um visor in-app (`file_viewer.py`); os demais abrem no SO
  (`os.startfile`).
- **Bridges** — "Conversar sobre" (Biblioteca→IA), "Transcrever" (Biblioteca→Transcrição) — via
  `navigate_to` com payload ([`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §4.4).

O **Mapa** é a projeção 2D do ML ([`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md)
§3): cada documento um ponto, agrupados por assunto. Auto-tags (YAKE) e dedup de imagens (dHash)
também vêm do ML — mas isso é superfície da Sessão 5; aqui só se **exibe** o resultado.

## Novidade 4 — CLI read-only

A CLI da Biblioteca (`library list`/`stats`/`dedup-images`) segue a taxonomia **read-only core-direto**
([`../conceitos/CLI.md`](../conceitos/CLI.md) §4.1): sem `CLIEventBus`, sem pipeline — chama o core
direto e imprime. É o par natural de um hub que não processa nada.

---

# Perguntas de fixação (comparativas)

1. A Biblioteca não tem `worker.py` nem contrato de eventos. Por que ela ainda é um "módulo"? O que
   define um módulo no projeto?
2. Como o hub "sabe" o que você já produziu, sem manter estado próprio? (dica: scanner + dirs
   canônicos)
3. As thumbnails são geradas numa thread daemon. Por que a repintura é **escopada** (`controle.update()`)
   e nunca `page.update()`? Ligue à regra do spinner.
4. A Biblioteca reusa `render_first_page_png` do Documentos e a projeção 2D do ML. Que princípio
   transversal isso mostra?
5. Por que a CLI da Biblioteca não usa `CLIEventBus`, enquanto a do Vídeo usa? (ligue à taxonomia do
   [`../conceitos/CLI.md`](../conceitos/CLI.md))

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Porque "módulo" no projeto = uma entrada em `MODULES` com um `control` (e ganchos de ciclo de
   vida) — não implica pipeline. A Biblioteca prova a definição.
2. O scanner **lê o disco a cada visita**, varrendo os dirs canônicos das constantes de `utils.py`.
   Como todo módulo grava no seu dir canônico, o hub não precisa de estado próprio.
3. `page.update()` global é caro e mata animações em curso (regra do spinner); o update **escopado**
   no item repinta só a thumbnail que chegou. Mesmo cuidado de repintura, agora sem pipeline.
4. Fonte única / reúso cross-módulo: poucos motores (render de PDF, projeção 2D, YAKE, dHash), muitos
   usos — a Biblioteca só **exibe** resultados de motores que moram alhures.
5. Porque `library` é **read-only core-direto** (rápido, síncrono, sem progresso): chama o core e
   imprime. O `video` é **pipeline** (longo, com progresso/cancelamento) → precisa do bus.

</details>

## Desafios

- **D1 (e se...?)** E se as thumbnails fossem geradas na **thread da UI**, item a item, ao abrir a
  Grade com 200 arquivos? Descreva a experiência do usuário.
- **D2 (projete)** Card de um `.csv` deve ganhar a ação **"Analisar nos Dados"**. Como implementar,
  usando um mecanismo que a Biblioteca já usa para Transcrição e IA?
- **D3 (ache o bug)** Um PR adiciona um kind novo ao scanner varrendo a string literal
  `"output/novomodulo/processed"`. Funciona hoje. Que fragilidade isso introduz, e qual é o jeito
  certo?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — A tela **congela** até a última miniatura: renderizar 200 PDFs/vídeos é trabalho pesado, e
  na thread da UI nada repinta nem responde a clique enquanto roda. Por isso a thread daemon + update
  **escopado** por item: a grade aparece na hora e as miniaturas vão "pipocando" sem travar nada.
- **D2** — Uma **bridge**: o card chama `navigate_to("data", {"file": path})`; o `on_mount` do módulo
  Dados recebe o payload e pré-carrega o arquivo como fonte da consulta. É exatamente o mecanismo de
  "Transcrever" (Biblioteca→Transcrição) e "Conversar sobre" (Biblioteca→IA) — nenhuma infraestrutura
  nova.
- **D3** — Duplica o caminho canônico como string solta: se a constante de `utils.py` mudar, o
  scanner quebra em silêncio (varre uma pasta que não existe mais). O certo: importar a constante
  (`NOVOMODULO_PROCESSED_DIR`) de `utils.py` — fonte única de caminhos, a mesma razão de o scanner
  funcionar para todos os outros módulos.

</details>
