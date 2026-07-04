# Perfis de Análise — seleção na GUI + prompts detalhados

> **Status (implementado):** Tier 1 entregue — pacote puro `src/analysis/`
> (`types`/`prompts`/`report` + catálogo `profiles/` por grupo) com 7 perfis:
> `default` (esquema legado byte-a-byte), `lecture`, `interview`, `tutorial`,
> `scientific`, `administrative`, `notes`. `analyze(..., profile=...)` gera
> prompt/relatório a partir dos `fields`. Selecionável via CLI `transcribe --profile`,
> seletor GUI agrupado (`gui/components/profile_selector.py`, reusado em
> Transcrição e Documentos→Analisar) e param `profile` do passo `transcription.analyze`
> (Receitas). O **mecanismo de disclaimer** está pronto e testado; os perfis
> `legal`/`health`/`review`/`news`/`pitch`/`sermon`/`literary` ficam para promoção
> futura (uma entrada no catálogo cada).

> Estende o `src/analyzer.py` de **um schema fixo** (10 campos, afinado para vídeo)
> para **vários perfis** selecionáveis. Cobre (1) a UI de seleção por cards com
> ícones, repensada para muitos tipos, e (2) os prompts detalhados de cada perfil.
>
> Convenções mantidas: prompts e saída em **PT-BR**; identificadores/JSON em inglês;
> tradução PT-BR e merge continuam genéricos.

---

## 1. Por que repensar a UI

Os módulos Imagem/Áudio usam grade de cards onde **cada operação revela um form
diferente**. Perfil de análise é mais simples — escolher o perfil **não** muda o
formulário, só troca o prompt/schema que roda. O desafio é o **número**: 7–13
perfis num grid plano cansam a leitura. Solução: **grade de cards com ícone,
agrupada em seções rotuladas**, dentro do form de Transcrição, exibida só quando o
switch **"Analisar"** está ligado.

### Layout (form de Transcrição, 380px)

```
☑ Analisar           Modelo: [gemini-2.5-flash ▾]
Tipo de análise:
 ── Conteúdo / Mídia ───────────────
 [▦ Geral] [🎓 Aula] [🎙 Entrevista]
 [🔧 Tutorial] [📰 Notícia]
 ── Acadêmico / Documento ──────────
 [🔬 Científico] [🗂 Administrativo] [⚖ Jurídico]
 ── Criativo ───────────────────────
 [📖 Literatura] [⭐ Resenha] [⛪ Sermão]
 ── Rápido ─────────────────────────
 [💡 Notas]
```

> (Esquema textual, não um diagrama.)

- Cada card: `ft.Icon` + rótulo curto, num `GestureDetector(mouse_cursor=Cursor.interactive)` — **sem `ink=True`**. Selecionado = borda/fundo dourado (`Color.primary`); demais em `surface`/`outline_variant`.
- Seções via `section_label(...)` do design system. Tudo num `ft.Column(scroll=AUTO)` (a lista é alta).
- Um perfil ativo por vez; persistido em `settings` (`last_analysis_profile`).
- 2–3 cards por linha cabem nos 380px (chips compactos). Reaproveita a linguagem visual dos cards da Home.
- **Invocar a skill `design-system`** ao construir (tokens, cores de acento por seção, cursores, help icon por perfil).

> Alternativa se crescer muito: filtro/busca por nome (TextField) acima da grade —
> mas com ~13 perfis agrupados, a grade rolável basta. Evitar `ft.SearchBar` (bugado).

---

## 2. Abstração (recap)

```python
@dataclass(frozen=True)
class Field:
    key: str       # chave JSON
    title: str     # título da seção no relatório
    kind: str      # "paragraph" | "list" | "quotes" | "keyvalue"
    rule: str      # instrução do campo (vira regra no prompt)

@dataclass(frozen=True)
class AnalysisProfile:
    id: str
    label: str            # rótulo PT-BR (card)
    icon: str             # ft.Icons.* (só referência; a GUI resolve)
    persona: str          # 1ª linha do system prompt
    source_hint: str      # "transcrição de vídeo" | "documento" | "gravação de reunião"...
    fields: list[Field]
    temperature: float = 0.4
    disclaimer: str = ""  # inserido no topo do relatório (jurídico/saúde)
```

`build_analysis_prompt(profile)` e `build_merge_prompt(profile)` **geram** o schema
JSON + regras a partir de `fields` (acaba a triplicação atual). `_format_report`
itera `fields` despachando por `kind`. Adicionar perfil = **uma entrada** no
`PROFILES`. `analyze(..., profile="default")`; CLI `--profile`.

**Template do system prompt gerado** (comum a todos):

```
{persona} Você recebe a {source_hint} e deve produzir uma análise estruturada
em formato JSON. Responda APENAS com JSON válido, sem texto extra antes ou depois.
Responda SEMPRE em português brasileiro.

Estrutura JSON obrigatória:
{ <campos do perfil> }

Regras:
- <para cada Field: "{key}: {rule}">
```

`kind` controla a renderização no relatório: `paragraph` (texto), `list` (bullets),
`quotes` (blockquote `>`), `keyvalue` (formato "Termo: definição").

---

## 3. Catálogo de perfis (prompts detalhados)

Cada perfil abaixo lista: persona · `source_hint` · temperatura · campos (`key` ·
título · kind) com a **regra detalhada** que entra no prompt. As regras seguem o
estilo do `ANALYSIS_PROMPT` atual (frases completas, "lista vazia se nenhum",
exemplos concretos quando ajudam).

### 3.1 `default` — Geral / Padrão  ·  ícone `ARTICLE_OUTLINED`  ·  temp 0.4
**Persona:** "Você é um analista especialista." · **source_hint:** "transcrição de um vídeo do YouTube"
Mantém os **10 campos atuais** (summary, key_points, action_items, key_concepts,
tools_mentioned, metrics, quotes, assumptions, vocabulary, sentiment_arc) com as
regras já existentes em `analyzer.py` — incluindo "IGNORE CTAs/patrocinadores"
(regra **exclusiva dos perfis de vídeo**). É a base; não reescrevo aqui.

### 3.2 `literary` — Literatura  ·  ícone `MENU_BOOK_OUTLINED`  ·  temp 0.55
**Persona:** "Você é um analista literário e crítico textual."
**source_hint:** "transcrição de um texto literário (narrado ou lido)"

- `summary` · Sinopse · paragraph — "3-5 frases resumindo o enredo/conteúdo sem revelar reviravoltas finais (evite spoilers do desfecho)."
- `themes` · Temas centrais · list — "Os temas e questões centrais da obra (amor, poder, identidade...); cada item explica COMO o tema aparece, não só o rótulo; mínimo 10 palavras."
- `characters` · Personagens · keyvalue — "Formato 'Nome: papel e arco'. Ex: 'Capitu: figura ambígua cujo olhar oblíquo sustenta a dúvida central da narrativa'. (lista vazia se não houver)."
- `narrative_structure` · Estrutura narrativa · paragraph — "Foco narrativo (1ª/3ª pessoa, narrador confiável?), tratamento do tempo (linear, flashback) e organização do enredo."
- `style_tone` · Estilo e tom · paragraph — "Registro (formal/coloquial), ritmo e tom predominante; cite recursos característicos do autor."
- `literary_devices` · Figuras de linguagem · list — "Metáforas, ironias, aliterações etc., cada uma com um exemplo curto do texto. (lista vazia se nenhuma)."
- `symbolism` · Símbolos e motivos · list — "Objetos/imagens recorrentes e o que representam. (lista vazia se nenhum)."
- `setting` · Ambientação · paragraph — "Tempo e espaço da narrativa e sua função no significado."
- `notable_passages` · Passagens marcantes · quotes — "Até 5 trechos quase literais esteticamente ou tematicamente significativos. (lista vazia se nenhum)."
- `interpretation` · Leitura crítica · paragraph — "Uma interpretação fundamentada do que a obra propõe; apresente como leitura possível, não como verdade única."

### 3.3 `scientific` — Artigo Científico  ·  ícone `SCIENCE_OUTLINED`  ·  temp 0.2
**Persona:** "Você é um revisor científico rigoroso."
**source_hint:** "transcrição de uma apresentação ou artigo acadêmico"

- `abstract` · Resumo · paragraph — "3-5 frases sintetizando objetivo, método e principal achado."
- `research_question` · Pergunta/objetivo · paragraph — "A pergunta de pesquisa ou objetivo central, em uma a duas frases."
- `hypotheses` · Hipóteses · list — "Hipóteses testadas, formuladas como afirmação. (lista vazia se nenhuma)."
- `methodology` · Metodologia · paragraph — "Desenho do estudo, amostra/dados, instrumentos e procedimentos. Seja específico sobre N, técnicas e controles quando mencionados."
- `results` · Resultados · list — "Principais resultados COM os números/estatísticas citados (p-valor, efeito, %); cada item é uma frase completa. (lista vazia se nenhum)."
- `conclusions` · Conclusões · list — "O que os autores concluem a partir dos resultados."
- `limitations` · Limitações · list — "Limites metodológicos reconhecidos ou inferíveis. (lista vazia se nenhuma)."
- `contributions` · Contribuições · list — "O que há de novo/original frente ao estado da arte."
- `key_concepts` · Conceitos-chave · keyvalue — "Formato 'Termo: definição de uma linha'. (lista vazia se nenhum)."
- `references_mentioned` · Referências citadas · list — "Autores, obras ou trabalhos mencionados. (lista vazia se nenhuma)."
- `future_work` · Trabalhos futuros · list — "Direções de pesquisa sugeridas. (lista vazia se nenhuma)."

### 3.4 `administrative` — Documento Administrativo / Reunião  ·  ícone `BUSINESS_CENTER_OUTLINED`  ·  temp 0.2
**Persona:** "Você é um secretário executivo que produz atas precisas."
**source_hint:** "gravação de uma reunião ou documento administrativo"

- `executive_summary` · Resumo executivo · paragraph — "3-5 frases com o essencial do que foi tratado e decidido."
- `decisions` · Decisões · list — "Decisões efetivamente tomadas, cada uma como afirmação clara. (lista vazia se nenhuma)."
- `action_items` · Ações · keyvalue — "Formato 'Tarefa — responsável (prazo)'. Ex: 'Enviar proposta — Marina (até 20/06)'. Se responsável/prazo não forem ditos, escreva 'responsável não definido'. (lista vazia se nenhuma)."
- `participants` · Participantes · list — "Pessoas/áreas mencionadas como presentes ou envolvidas. (lista vazia se não identificável)."
- `deadlines` · Prazos e datas · list — "Datas e prazos citados com seu contexto. (lista vazia se nenhum)."
- `risks_issues` · Riscos e pendências · list — "Problemas, bloqueios ou riscos levantados. (lista vazia se nenhum)."
- `agreements` · Acordos · list — "Consensos/combinados que não são decisões formais. (lista vazia se nenhum)."
- `open_questions` · Questões em aberto · list — "Pontos não resolvidos que ficaram pendentes. (lista vazia se nenhum)."
- `next_steps` · Próximos passos · list — "Encaminhamentos e próxima reunião, se mencionada."

### 3.5 `lecture` — Aula / Educacional  ·  ícone `SCHOOL_OUTLINED`  ·  temp 0.3
**Persona:** "Você é um tutor que transforma aulas em material de estudo claro."
**source_hint:** "transcrição de uma aula ou conteúdo educacional"

- `summary` · Resumo · paragraph — "3-5 frases com o que a aula ensina, no todo."
- `learning_objectives` · Objetivos de aprendizagem · list — "O que o aluno deve saber/fazer ao final; comece cada item com um verbo (compreender, calcular, aplicar...)."
- `key_concepts` · Conceitos-chave · keyvalue — "Formato 'Termo: definição clara de uma a duas linhas', em ordem didática."
- `step_by_step` · Passo a passo · list — "Se a aula ensina um procedimento, os passos em ordem; cada passo autoexplicativo. (lista vazia se não aplicável)."
- `examples` · Exemplos · list — "Exemplos concretos usados para ilustrar os conceitos. (lista vazia se nenhum)."
- `formulas` · Fórmulas e regras · list — "Fórmulas, leis ou regras enunciadas, com o que cada símbolo significa. (lista vazia se nenhuma)."
- `common_mistakes` · Erros comuns · list — "Equívocos/armadilhas que o professor alerta. (lista vazia se nenhum)."
- `study_questions` · Perguntas de revisão · list — "3-7 perguntas que testam a compreensão do conteúdo (sem as respostas)."
- `glossary` · Glossário · keyvalue — "Termos técnicos do tema, formato 'Termo: definição'. (lista vazia se nenhum)."

### 3.6 `interview` — Entrevista / Podcast  ·  ícone `MIC_OUTLINED`  ·  temp 0.35
**Persona:** "Você é um produtor de conteúdo que sintetiza conversas."
**source_hint:** "transcrição de uma entrevista ou podcast"

- `summary` · Resumo · paragraph — "3-5 frases sobre o que foi conversado e os destaques."
- `participants` · Participantes · keyvalue — "Formato 'Nome/papel: como contribui na conversa'. Se a transcrição não distinguir falantes, registre 'falantes não rotulados' e atribua no melhor esforço."
- `main_topics` · Temas abordados · list — "Os assuntos principais, na ordem em que surgem."
- `positions` · Opiniões e posições · list — "Posicionamentos defendidos; quando possível, atribua a quem ('Fulano defende que...'). (lista vazia se nenhuma)."
- `notable_quotes` · Frases marcantes · quotes — "Até 6 falas quase literais que sintetizam bem uma ideia, com mínima atribuição. (lista vazia se nenhuma)."
- `anecdotes` · Histórias e casos · list — "Anedotas/relatos pessoais contados. (lista vazia se nenhum)."
- `recommendations` · Recomendações · list — "Livros, ferramentas, pessoas ou recursos citados como recomendação. (lista vazia se nenhum)."
- `disagreements` · Divergências · list — "Pontos de discordância ou tensão entre os participantes. (lista vazia se nenhum)."

### 3.7 `tutorial` — Tutorial / How-to / Receita  ·  ícone `CHECKLIST`  ·  temp 0.2
**Persona:** "Você é um redator técnico que documenta procedimentos."
**source_hint:** "transcrição de um tutorial ou receita"

- `goal` · Objetivo · paragraph — "O que se constrói/alcança ao final, em uma a duas frases."
- `prerequisites` · Requisitos · list — "Materiais, ingredientes, ferramentas ou conhecimentos prévios necessários. (lista vazia se nenhum)."
- `steps` · Passo a passo · list — "Os passos EM ORDEM, numerados implicitamente; cada passo é uma instrução acionável e completa; preserve quantidades/tempos citados."
- `tips_warnings` · Dicas e avisos · list — "Dicas, atalhos e advertências de segurança/erro. (lista vazia se nenhum)."
- `common_mistakes` · Erros comuns · list — "O que costuma dar errado e como evitar. (lista vazia se nenhum)."
- `expected_result` · Resultado esperado · paragraph — "Como saber que deu certo (aparência, comportamento, métrica)."
- `time_cost` · Tempo e custo · list — "Tempo estimado, rendimento, custo ou dificuldade, se mencionados. (lista vazia se nenhum)."

---

## 4. Perfis adicionais (campos definidos — prompt a finalizar)

Mesma mecânica; campos prontos, regras a detalhar quando forem promovidos.

- **`news` — Notícia / Jornalístico** · `NEWSPAPER` · temp 0.2 — campos: `who`, `what`, `when`, `where`, `why`, `how`, `sources_cited`, `facts_vs_opinion` (separa fato de opinião), `context`, `implications`.
- **`review` — Resenha / Crítica** · `RATE_REVIEW_OUTLINED` · temp 0.4 — `subject`, `pros`, `cons`, `verdict`, `comparisons`, `recommended_for`.
- **`pitch` — Pitch / Negócios** · `TRENDING_UP` · temp 0.3 — `value_proposition`, `market`, `business_model`, `financials`, `competition`, `the_ask`, `next_steps`.
- **`sermon` — Sermão / Palestra motivacional** · `SELF_IMPROVEMENT` · temp 0.4 — `central_message`, `passages_cited`, `lessons`, `illustrations`, `call_to_action`.
- **`notes` — Notas / Brainstorm** · `LIGHTBULB_OUTLINE` · temp 0.3 — `ideas`, `decisions`, `todos`, `questions`, `insights`. (Leve, para memo de voz.)

### Perfis com aviso obrigatório (disclaimer no relatório)

- **`legal` — Jurídico** · `GAVEL` · temp 0.2 — `parties`, `facts`, `arguments`, `statutes_cited`, `decision_or_request`, `deadlines`, `risks`.
  **disclaimer:** "⚠ Síntese informativa gerada por IA — **não** constitui aconselhamento jurídico."
- **`health` — Saúde (informativo)** · `HEALTH_AND_SAFETY_OUTLINED` · temp 0.2 — `topic`, `symptoms`, `causes`, `treatments_mentioned`, `recommendations`, `sources`.
  **disclaimer:** "⚠ Conteúdo informativo gerado por IA — **não** substitui avaliação médica profissional."

O `disclaimer` é inserido pelo `_format_report` no topo do `.md` quando presente.

---

## 5. Notas de implementação

- **Temperatura por perfil** (campo do `AnalysisProfile`): criativo/interpretativo mais alto (literatura 0.55), factual mais baixo (científico/administrativo/jurídico 0.2). Hoje é fixa em 0.4.
- **Regra "ignore CTAs/patrocinadores"** entra só nos perfis de vídeo (via `source_hint`/flag), não nos de documento/reunião.
- **Merge e tradução PT-BR continuam genéricos** — passam a ler o schema do perfil ativo (gerado de `fields`), em vez do schema fixo.
- **Atribuição de falante** (entrevista) é "melhor esforço" enquanto não houver diarização (a transcrição atual não rotula falantes).
- **Persistência:** `settings` ganha `last_analysis_profile` (default `"default"`).
- **CLI:** `uv run main.py transcribe <URL> --analyze --profile lecture`.
- **Testes** (skill `testing`): cada perfil testável com `GenericFakeChatModel` — basta um fake retornando JSON com as chaves do perfil e asserir que `_format_report` rende as seções certas; e que `build_analysis_prompt(profile)` inclui todas as chaves. Cobrir 1 perfil com disclaimer (verificar que o aviso aparece no topo).
- **Compatibilidade:** `profile="default"` reproduz exatamente o comportamento atual — refactor sem regressão.
```
