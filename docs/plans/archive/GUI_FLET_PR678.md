# GUI Flet 0.85 — viabilidade e design para PR6, PR7 e PR8

> Mapa do que é **possível / difícil / impossível** na GUI (Flet 0.85.2) para os
> próximos planos, mais a evolução de estrutura/design para 8 módulos ficarem
> apresentáveis. Complementa a skill `design-system` (`.claude/skills/design-system/SKILL.md`)
> e a seção "Flet 0.85 — quirks críticos" do `CLAUDE.md`.
>
> **Veredito geral: o Flet 0.85 dá conta de PR6, PR7 e PR8 inteiros.** Chat, grade
> de cards e editor de sequência reordenável são todos viáveis. O único padrão
> genuinamente espinhoso (tabela grande) pertence a um eventual PR9 (Dados), não
> aos três atuais.

---

## 1. Princípio: polimorfismo de layout (já suportado)

O contrato `Module` (`src/gui/modules/base.py`) aceita um `control` **arbitrário** —
cada módulo define o próprio layout. Isso já existe e é a chave: os novos módulos
**não** precisam usar o split `form 380px | painel` dos módulos de processamento.

| Módulo | Layout |
|---|---|
| Áudio / Vídeo / Imagem / Transcrição / Documentos | split `form 380px \| painel` (atual) |
| **Biblioteca (PR6)** | tela cheia: barra de filtro no topo + grade |
| **IA (PR7)** | form de pergunta + painel de chat |
| **Receitas (PR8)** | lista de presets + editor de sequência |

O `navigate_to` (alterna `visible=` num `ft.Stack`) **escala para 8 módulos sem
mudança** — não é preciso migrar para o Router (ver §6).

---

## 2. Mapa de viabilidade por PR

| PR | Necessidade GUI | Veredito | Como (no padrão do projeto) |
|---|---|---|---|
| **PR6** | grade de cards + filtro + busca + thumbnails | **Possível** | `ft.GridView` (lazy nativo); `segmented_selector` (filtro por tipo); **`ft.TextField`** (busca — **não** `SearchBar`); `ft.Image(bytes)` (thumb). Risco: perf com **milhares** de itens (#6270) → cap/paginação + updates escopados. |
| **PR7** | chat rolável + resposta markdown + fontes + streaming | **Possível** | `ft.ListView(auto_scroll=True)`; **`ft.Markdown`** (resposta com citações `[n]`); `output_card` (fontes); streaming = atualizar `.value` por token + `control.update()` escopado (o 0.83 deixou o diffing ~6,7× mais rápido; reusa o padrão `mutable=True` do log). |
| **PR8** | rodar presets + **editor de sequência reordenável** + validação ao vivo | **Possível** | `ft.ReorderableListView` (reordenar passos via drag — **nativo**, `on_reorder` reordena a lista); menu para adicionar passo; `visible=` para expandir params; `validate_recipe` no `on_change` desabilita "Rodar". |

> **Correção registrada:** versões anteriores do plano do PR8 diziam que drag-drop
> "não era nativo". **É.** O Flet 0.85 tem `ft.ReorderableListView` (lista
> reordenável por arrasto) e `ft.Draggable` + `ft.DragTarget` (arrastar entre
> alvos por grupo). O editor de receitas pode usar `ReorderableListView` direto.

---

## 3. Possível / difícil / impossível no Flet 0.85

### Possível (nativo, recomendado)

- **`ft.GridView`** — grade com renderização lazy (só o visível + `cache_extent`). PR6.
- **`ft.ListView`** — lista lazy com `auto_scroll`. Log e chat (PR7).
- **`ft.Markdown`** — renderiza markdown (resposta de IA com citações). PR7.
- **`ft.ReorderableListView`** — reordenar por arrasto (`on_reorder`). PR8.
- **`ft.Draggable` / `ft.DragTarget`** — drag-and-drop por grupo (alternativa ao reorder). PR8.
- **`ft.Image(bytes)`** — aceita bytes direto (thumbnails sem base64). PR6.
- **Streaming de texto** — atualizar `.value` repetidamente + update escopado (0.83 tornou o `.update()` ~6,7× mais rápido e elimina updates redundantes). PR7.
- **`ft.use_dialog()`** (0.85) — dialogs reativos para modais (confirmar exclusão, configurar passo). PR6/PR8.

### Difícil (possível com cuidado/extensão)

- **Grade com milhares de itens** — `GridView` degrada o `page.update()` no 0.80+ (#6270). Mitigar: cap/paginação (ex.: 120/página), **updates escopados** (`control.update()`, nunca `page.update()` na thread de thumbs), card enxuto (evitar `Container` aninhado por célula).
- **Tabela tabular grande** (futuro PR9 Dados) — `ft.DataTable` core **não é virtualizado** e já travou com muitos dados. Saída: paginar ou usar a extensão **`flet-datatable2`** (headers fixos, colunas dimensionáveis). Fora de PR6-8, mas registrar.
- **Reordenar listas longas** — `ReorderableListView` é fluido para dezenas de itens; receitas têm poucos passos, então é tranquilo.

### Impossível / a evitar (teto do Flet ou quirk do projeto)

- **`ft.Audio`** — não existe; usar sounddevice + ffmpeg (já feito no `audio_player.py`).
- **`ft.SearchBar`** — bugado em `on_change`/rebuild → usar `ft.TextField`.
- **`ft.Tabs`** — quebra com `object_patch IndexError` → abas/menus manuais + `visible=`.
- **`page.update()` em cascata** — `IndexError` no `object_patch` → um update por evento; updates escopados.
- **`DataTable` virtualizada de verdade** — não é nativa.
- **Editor rich-text / WYSIWYG** e **visualizações desenhadas** além do `ft.Canvas` — inviáveis ou muito trabalhosos (e fora do escopo: o projeto não usa diagramas/visualizações).

---

## 4. Novas factories do design system

Os 5 módulos atuais compartilham factories em `src/gui/theme/components/`. PR6-8
pedem 3 novas peças compartilhadas — **construir invocando a skill `design-system`**,
mantendo tokens (`Color`/`Space`/`Radius`/`Motion`/`Type`), `Cursor.*`, help system,
sem `ink=True`, com `GestureDetector` para clique.

| Factory | Onde | Para | Esboço |
|---|---|---|---|
| **`item_card(item, on_open, on_route, accent)`** | `components/cards.py` (ou módulo Biblioteca) | célula da grade do PR6 | thumb (`ft.Image(bytes)`) ou ícone de tipo + nome + badge de categoria + tamanho/data; `GestureDetector(mouse_cursor=Cursor.interactive)`; ações Abrir/Enviar. |
| **`answer_block(text, sources, streaming)`** | módulo IA | resposta do RAG no PR7 | `ft.Markdown` (citações `[n]`) + lista de `output_card` (fontes); modo streaming atualiza o valor por token. |
| **`step_row(spec, params, on_remove)`** | módulo Receitas | linha de passo reordenável no PR8 | rótulo do passo + resumo de params + expandir (`visible=`) + botão remover; vive dentro de um `ft.ReorderableListView`. |

> Cada factory segue o padrão das existentes: retorna um `ft.Control`, usa tokens
> em vez de px hardcoded, e cor de acento por tipo reaproveitando o mapa da Home
> (`Color.log.ok` áudio, `Color.log.info` vídeo, etc.). Cards clicáveis **nunca**
> usam `ink=True`.

---

## 5. Navegação e Home para 8 módulos

8 módulos: Áudio, Vídeo, Imagem, Transcrição, Documentos, **Biblioteca**, **IA**, **Receitas**.

### NavigationRail

A rail atual (80px, `label_type=ALL`) comporta 8 destinos — ela rola se faltar
altura. **Limitação:** `ft.NavigationRailDestination` é **plana**, sem rótulos de
grupo. Se você quiser seções visuais ("Processar / Conteúdo / Automação"):

- **Opção A (recomendada, simples):** manter a rail plana com 8 ícones — claro o
  suficiente, zero custo.
- **Opção B:** rail custom (uma `Column` de `GestureDetector` + ícones com rótulos
  de grupo) — controle total, mais trabalho; só se a seção agregar valor real.
- **Opção C:** `ft.NavigationDrawer` (suporta divisores/rótulos) — muda o padrão
  de navegação; provavelmente exagero aqui.

### Home

Com 8 cards a Home fecha limpo em **4×2** (4 por fileira, 2 fileiras), eliminando
o atual hack de `expand=2`/spacers (que existia para centralizar a 2ª fileira de 5
cards). Opcional: rótulos de seção acima dos grupos — puramente visual, custo baixo.
(O PR7 leva a Home a 7 — use 4+3 transitório; com PR8 chega a 8 e fecha em 4×2.)

---

## 6. Router e dialogs do 0.85

O Flet 0.85 introduziu um **Router declarativo** (rotas aninhadas, outlets,
view-stack nativo) e **`ft.use_dialog()`** (dialogs reativos).

- **Router:** **não migrar.** A navegação por visibilidade num `ft.Stack` foi
  escolhida deliberadamente para fugir do `object_patch IndexError` do `ft.Tabs`,
  e escala para 8 módulos sem custo. Migrar seria refactor grande sem ganho.
- **`use_dialog()`:** **vale adotar** quando precisar de modais — confirmar
  exclusão (Biblioteca), configurar um passo (Receitas), avisos de privacidade
  do Gemini (IA). Mais limpo que `page.show_dialog()` imperativo.

---

## 7. Performance — regras práticas

- **Nunca** `page.update()` dentro de loop/thread; use `control.update()` escopado
  (regra de ouro reforçada pelos ganhos do 0.83 e pelo bug #6270).
- **GridView (PR6):** cap/paginação + thumbs em thread atualizando cada card
  individualmente (padrão das duas threads do `audio_player`).
- **Chat (PR7):** streaming atualiza só a última bolha/linha (`mutable`), não a lista toda.
- **DataTable (futuro PR9):** paginar ou `flet-datatable2`; nunca jogar milhares de
  linhas de uma vez.

---

## 8. Resumo

Nada em PR6-8 esbarra no teto do Flet 0.85 — inclusive o editor reordenável do PR8
é **nativo** (`ReorderableListView`). A arquitetura de módulos já dá polimorfismo
de layout; o que cresce é o design system (3 factories novas) e a Home (4×2). O
único cuidado transversal é **performance de listas/grades grandes** (updates
escopados + cap), e o único padrão realmente trabalhoso — **tabela grande** — fica
para um eventual PR9, não para os três atuais.

---

## Fontes

- [ReorderableListView — Flet](https://flet.dev/docs/controls/reorderablelistview/)
- [Draggable — Flet](https://flet.dev/docs/controls/draggable/) · [DragTarget — Flet](https://flet.dev/docs/controls/dragtarget/) · [Drag and Drop cookbook — Flet](https://docs.flet.dev/cookbook/drag-and-drop/)
- [Markdown — Flet](https://flet.dev/docs/controls/markdown/)
- [DataTable — Flet](https://docs.flet.dev/controls/datatable/) · [flet-datatable2 (PyPI)](https://pypi.org/project/flet-datatable2/) · [DataTable freezes (issue #3078)](https://github.com/flet-dev/flet/issues/3078)
- [GridView slowdown com muitos itens (issue #6270)](https://github.com/flet-dev/flet/issues/6270)
- [Flet 0.85 — Router, dialogs e mais (release)](https://flet.dev/blog/flet-v-0-85-release-announcement/)
- [Large Lists (lazy ListView/GridView) — Flet](https://docs.flet.dev/cookbook/large-lists/)
