# Plano — Correções do `src/analysis/`

> **Origem**: avaliação exploratória arquivo-a-arquivo (sessão Cowork, jul/2026). 9 arquivos / ~1.296
> linhas (`__init__`, `types`, `prompts`, `report` + `profiles/{__init__,media,documents,creative,quick}`).
> Pacote recente e bem desenhado (catálogo declarativo, puro, sem duplicação de prompt). Os achados
> se concentram em **um tema**: `report.py` confia que o LLM respeitou os tipos do schema à risca —
> qualquer desvio de shape (str↔list, dict, itens não-string) vira lixo silencioso no relatório.
> Secundário: integridade do catálogo não é validada (typo em `kind`, drift PROFILES×GROUPS).

## Checklist ativo de salvaguardas

| Salvaguarda | Resultado em `src/analysis/` |
|---|---|
| Pureza (sem Flet/LangChain onde prometido) | **OK** — `types`/`report`/`profiles` puros; LangChain só em `prompts` |
| Tolerância a output malformado de LLM | **FALHOU** — `report._render_section` assume tipos exatos; ver Fase 1 |
| Validação de catálogo | **FALHOU** — `Field.kind` é string livre (`ALL_KINDS` existe mas ninguém valida); GROUPS lista ids na mão sem checagem contra PROFILES |
| Duplicação | **OK** — prompts/report gerados dos fields; nenhuma cópia |
| Docstrings/idioma | **OK** — EN em código, PT só em conteúdo de prompt/label (correto: é texto de interface) |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Robustez do `report.py` a desvios de schema |
| 2 | Validação de integridade do catálogo |
| 3 | Refinos de prompt |
| 4 | Higiene |
| 5 | Verificação |

---

## Fase 0 — Baseline
`uv run pytest -m unit` verde antes de tocar qualquer coisa.

## Fase 1 — [BUG] `report._render_section` renderiza lixo em desvio de shape

O prompt pede list-of-strings para list/quotes/keyvalue e string para paragraph, mas modelos locais
pequenos desviam com frequência. Hoje cada desvio degrada silenciosamente:

1. **String onde se espera lista** (list/quotes/keyvalue): `items = list(value)` faz **split
   caractere-a-caractere** — o relatório sai com um bullet por letra. É o pior caso e é plausível
   (modelo devolve o campo como frase única).
2. **Lista onde se espera parágrafo**: `str(value)` imprime o **repr Python** (`['a', 'b']`) no
   Markdown.
3. **Dict para keyvalue**: modelos interpretam 'Termo: definição' como objeto JSON. `_is_empty` não
   trata dict (devolve False até para `{}`) e `list(value)` itera só as **chaves** — as definições
   somem silenciosamente.
4. **Itens não-string dentro da lista** (ex.: `{"termo": ..., "definicao": ...}`): `f"- {item}"`
   imprime o repr do dict.

Fix único: um normalizador por kind antes de renderizar —
`str → [str]` para kinds de lista; `list → "\n\n".join` (ou `"; ".join`) para paragraph;
`dict → [f"{k}: {v}", ...]` para keyvalue (e `{}` tratado em `_is_empty`); item não-string dentro
de lista → coerção amigável (dict de 2 chaves → "chave1: chave2", senão `json.dumps` compacto).
Testes parametrizados cobrindo os 4 desvios × kinds.

Complementos menores no mesmo arquivo:
- **Seção `always` sem `empty_text`** (ex.: `key_points` do default): vazio renderiza o heading `##`
  sem corpo. Decidir: placeholder padrão ("—") ou exigir `empty_text` quando `always=True` (validação
  da Fase 2).
- **Quotes multilinha**: `f"> {quote}"` só cita a primeira linha; quebras internas escapam do
  blockquote. Prefixar cada linha.
- Itens que já começam com `"- "` viram bullet duplo — strip barato no normalizador.

## Fase 2 — Validação de integridade do catálogo

1. **`Field.kind` é string livre**: um typo num perfil novo (`"pargraph"`) cai silenciosamente no
   branch final de lista. `ALL_KINDS` existe e é exportado, mas nada valida contra ele. Fix:
   `__post_init__` em `Field` levantando `ValueError` para kind desconhecido (dataclass frozen aceita
   `__post_init__`). Aproveitar: validar `empty_text` obrigatório quando `always=True` (decisão da
   Fase 1) e `key` não vazio/duplicado dentro do perfil (em `AnalysisProfile.__post_init__`).
2. **Drift PROFILES × GROUPS**: `GROUPS` lista os ids na mão — um perfil adicionado ao módulo mas
   esquecido no grupo existe no CLI e some do seletor da GUI, sem aviso. Fix: teste unitário (ou
   assert de import em `profiles/__init__`) garantindo bijeção: todo id de `PROFILES` aparece em
   exatamente um `GroupMeta.profile_ids` e vice-versa.
3. Teste de sanidade do catálogo inteiro: para cada perfil, `build_analysis_prompt`/`build_merge_prompt`
   compilam e `format_report(profile, {}, ...)` não levanta — pega regressões de qualquer perfil novo
   de graça.

## Fase 3 — Refinos de prompt

1. **Placeholders ecoados**: modelos pequenos às vezes copiam os `"..."` do skeleton literalmente —
   viram bullets `...` no relatório. Duas frentes: regra extra no system ("Não copie os placeholders
   `...`; se não houver conteúdo, use lista vazia / string vazia") e filtro no normalizador da Fase 1
   (descartar item cujo strip seja `...`).
2. **Merge sem regra de `always`**: no merge, campos paragraph podem voltar `null`; hoje o skeleton
   não diz que summary/tldr são obrigatórios. Linha extra barata nas regras de consolidação
   ("nunca deixe {keys always} vazios").

## Fase 4 — Higiene

1. `report.format_report`: `datetime.now()` inline torna o output não-determinístico p/ teste —
   parâmetro opcional `generated_at: datetime | None = None` (default now) sem mudar call sites.
2. `report.py` linha 64: `# type: ignore[arg-type]` desaparece sozinho com o normalizador da Fase 1.
3. Docstring de `profiles/__init__` menciona "Tier 1" sem contexto no código — remover ou apontar
   para o plano/HISTORY correspondente.

## Fase 5 — Verificação

- `uv run pytest -m unit` verde; ruff limpo nos arquivos tocados.
- Golden test do perfil default: relatório byte-a-byte idêntico ao legado com input bem-formado
  (a promessa explícita do docstring de `report.py`) — garante que o normalizador não altera o
  caminho feliz.
- Smoke manual: `--analyze --profile flashcards` com modelo local pequeno (o cenário mais provável
  de desvio de shape) e inspeção do .md.
- Registrar rodada no `docs/HISTORY.md` e mover este plano para concluídos, conforme convenção.
