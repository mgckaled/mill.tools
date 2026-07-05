# Plano — Correções do `core/data/`

> **Origem**: avaliação exploratória arquivo-a-arquivo (sessão Cowork, jul/2026). 14 arquivos / ~1.450
> linhas. Mesmo formato do `PLANO_CORRECOES_QUARTETO_ML.md` (implementado): itens dizem *o quê* e *onde*;
> o *como* é da sessão de implementação (context7 para APIs de DuckDB/matplotlib/polars).
> Regras do projeto valem integralmente; `pytest -m unit` verde + `ruff` limpo por fase.

## Checklist ativo de salvaguardas (padrões recorrentes do quarteto ML — auditados neste pacote)

| Salvaguarda | Resultado em `core/data/` |
|---|---|
| Escritas não-atômicas (helper `core/io_atomic.py` existe desde o quarteto) | **FALHOU** — `store._write` (queries.json) e `assess.save_assessment` (cache) escrevem direto; ambos anteriores ao helper → migrar (Fase 2) |
| Timeouts herdados em gates de disponibilidade | **OK** — os gates de `frames`/`charts` são probes de import puro, sem rede |
| Duplicação de esqueleto intra-pacote | **OK dentro do pacote**; nota cross-pacote: `data/store.py` é a 3ª cópia do padrão "lista JSON de entradas nomeadas" (com `recipes/store` e `rag/templates`) — registrar, não corrigir agora |
| Docstring de pacote desatualizado | **OK** — `__init__.py` fiel |
| Strings PT no core sem justificativa | **PARCIAL** — mensagens de erro user-facing em PT em todo o pacote (`DataEngineError`, `ConvertError`, `ValueError` dos charts), enquanto `core/ml` usa EN. Não é bug; é convenção não resolvida → decidir e registrar (Fase 0) |

## Fases

| Fase | Tema |
|---|---|
| 0 | Decisão de convenção + baseline |
| 1 | Bugs reais (validate ×2, nl2sql ×1) — maior valor, independentes de tudo |
| 2 | Adoção do `io_atomic` + robustez |
| 3 | Perf e consistência de seams |
| 4 | Miudezas oportunistas |
| 5 | Verificação + docs |

---

## Fase 0 — Decisão + baseline

1. **Convenção de idioma para mensagens de erro user-facing no core**: `core/data` é todo PT
   ("Consulta vazia.", "Sem dados para plotar."), `core/ml` é EN ("k-means requires..."). Decidir uma regra
   (sugestão: exceções user-facing podem ser PT, pois chegam cruas à GUI/CLI — formalizar no CLAUDE.md
   "Convenções" e registrar no HISTORY). Não sair renomeando nada nesta fase — só decidir, para as fases
   seguintes escreverem mensagens novas já na convenção.
2. Baseline: suíte verde.

---

## Fase 1 — Bugs reais

1. **[BUG — o principal] `validate.ensure_select` proíbe a receita que o próprio engine recomenda.**
   `_FORBIDDEN` contém `"replace"` como palavra-inteira em qualquer posição — mas o docstring de
   `engine.reader_expr` (caso XLSX) recomenda literalmente
   `CAST(replace(replace(col,'.',''),',','.') AS DOUBLE)` para números em formato pt-BR. Essa consulta é
   **rejeitada** pelo validador ("Palavra-chave não permitida: 'replace'") — o fluxo XLSX brasileiro está
   quebrado por contradição entre dois arquivos. Fix sugerido: remover `"replace"` da lista — como função,
   `replace()` não muta nada, e o caso perigoso (`CREATE OR REPLACE`) já é capturado por `"create"`.
   Auditar na mesma passada as demais palavras da lista que colidem com nomes de função/coluna comuns
   (candidatas: nenhuma óbvia além de `replace`, mas confirmar). Adicionar teste de regressão com a
   consulta do docstring do engine.
2. **[BUG] Ponto-e-vírgula dentro de string literal rejeita consulta válida.** Em `ensure_select`, o check
   de múltiplos statements (`partition(";")`) roda **antes** do strip de literais — `WHERE col = 'a;b'`
   é rejeitada como "duas consultas". Fix: aplicar `_STRING_LITERal.sub` antes do check de `;` (mantendo o
   retorno do SQL original intacto).
3. **[BUG] `nl2sql._extract_payload` — fallback de SQL cru em bloco cercado nunca funciona.** Quando o
   modelo devolve ```` ```sql SELECT ...``` ```` sem JSON, o código faz `bare = candidates[1] if fenced`,
   mas com fence presente `candidates[0]` é o conteúdo do bloco e `candidates[1]` é o **texto bruto inteiro**
   (com as crases) — o `startswith(("select", ...))` falha e levanta `NL2SQLError` exatamente no caso que o
   fallback foi escrito para salvar. Fix: `candidates[0]`. Teste: resposta fenced-SQL-sem-JSON.

---

## Fase 2 — Adoção do `io_atomic` + robustez

1. Migrar `store._write` (queries.json) e `assess.save_assessment` (data_assessments.json) para o helper
   atômico do quarteto (`core/io_atomic.py`). São os dois FALHOU do checklist.
2. `nl2sql`/`assess`: tolerar `resp.content` como lista de blocos (o quarteto já corrigiu isso em
   `rag/chat.answer` — replicar o mesmo tratamento; ver como foi feito lá e reusar).
3. `data/ml.detect_outliers`: coluna numérica **toda-NaN** sobrevive ao `fillna(mean)` (média de NaN = NaN)
   e estoura erro críptico do sklearn — dropar colunas all-NaN antes (ou mensagem clara).

---

## Fase 3 — Perf e consistência de seams

1. **`datacard.card_for_path` escaneia o arquivo 3×**: `scan_file` próprio + `scan_file` dentro de
   `profile_text` + `preview` — cada um abre conexão DuckDB e o scan refaz `count(*)` (scan completo em
   CSV). Na indexação de vários arquivos de dados isso multiplica. Refatorar `profile_text` para aceitar um
   `DataFile` já escaneado (mantendo a assinatura por path como conveniência) e reusar no card.
2. **`describe_file` não aceita `connect_fn`** — único ponto do engine sem o seam injetável (preview/
   run_query/export/convert têm). Uniformizar.
3. **`frames.is_available` não prova pandas**, mas `to_pandas` exige (polars puxa lazy). Se o extra
   `[analysis]` sempre instala os três, é teórico — confirmar no pyproject e, se for o caso, só documentar;
   senão, incluir pandas no probe.

---

## Fase 4 — Miudezas oportunistas (ao tocar cada arquivo)

1. `engine.register_views` não repassa `sheet` — consultas sobre XLSX multi-planilha sempre usam a planilha
   default (só o `preview` seleciona sheet). Avaliar custo de propagar `sheet` no `DataFile`; se não valer
   agora, registrar como limitação conhecida no ROADMAP.
2. `view_name_for` pode gerar identificador igual a keyword SQL (`select.csv` → view `select`): o engine
   quota, mas o **modelo NL→SQL** recebe o nome cru no schema e tende a escrever `FROM select` sem aspas.
   Barato: sufixar nomes que caem em keywords comuns (ou quotar no `schema_text`).
3. `charts._line`/`_scatter` não coagem o eixo X numérico como `_bar` faz (Decimal/object do DuckDB pode
   tripar o category converter) — aplicar `_numeric` no X quando a coluna for numérica.
4. Registrar no ROADMAP (não corrigir): `charts.py` está **no teto** da régua (400 linhas — corte natural:
   heurísticas puras × renderers) e `engine.py` acima do alvo (384) — **dividir ao tocar** na próxima
   feature que os estender, conforme architecture §3.

---

## Fase 5 — Verificação + docs

1. Suíte completa verde (`unit` + `integration`); `ruff` limpo; cobertura dos módulos tocados sem regressão.
2. Testes novos citados nas Fases 1–3 presentes (regressão do `replace`, literal com `;`, fenced-SQL,
   all-NaN, card single-scan).
3. Atualizar o que os docs afirmam e este plano muda: CLAUDE.md §Dados continua correto ("validate rejeita
   DML/COPY/ATTACH" — segue verdade); conferir menções ao comportamento do validador na skill `cli`
   (gotcha do `--sql`) e nos arquivos de mock da skill `testing` (`test_validate`/`test_nl2sql`).
4. Entrada no `HISTORY.md` (inclui a decisão de convenção da Fase 0.1) e mover este plano para
   `docs/plans/implemented/`.

---

## Não-achados dignos de nota (para não "consertar" o que está certo)

- `schema_from_rows` testa `bool` **antes** de `int` — correto (bool é subclasse de int); não "simplificar".
- `_bar` plota por posições inteiras com labels explícitos — workaround documentado do category converter
  sobre Decimal; não trocar por `ax.bar(labels, ...)`.
- A paleta clara default dos charts é intencional (GUI injeta o tema escuro).
- `validate` continua sendo 1ª linha de defesa **por cima** de um engine in-memory sem nada gravável — a
  Fase 1 afrouxa apenas os falsos positivos, nunca o modelo de duas camadas.
