# Açaí Família — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL, em Clean Architecture
(`interfaces → application → domain`; `infrastructure` implementa as portas).

## Estrutura

```text
app/
├── config.py            # Settings
├── bootstrap/           # composition root: liga portas às implementações
├── domain/<modulo>/     # entidades e regras puras (sem frameworks)
├── application/         # casos de uso + portas (Protocol); unit_of_work.py = transação
├── infrastructure/      # persistence/<modulo>/{models,repository}, security, whatsapp, gemini
└── interfaces/http/     # routers, schemas, deps, errors, middleware
```

Regras: dependências apontam para dentro; routers só recebem casos de uso (nunca importam
`infrastructure`); módulos conversam por casos de uso/portas na mesma `UnitOfWork`.
Novo módulo com tabelas: registrar o modelo em `infrastructure/persistence/registry.py`.

## Rodando

```bash
cp .env.example .env          # edite SECRET_KEY
docker compose up --build     # sobe Postgres + API (aplica migrations)
docker compose exec api python -m scripts.create_admin
```

Local sem Docker (precisa do `.env`):

```bash
uv sync --extra dev   # instala tudo
uv run task db        # só o PostgreSQL
uv run task migrate   # aplica migrations
uv run task admin     # primeiro administrador
uv run task run       # API em http://localhost:8000/docs
```

Outras tarefas: `uv run task --list` (`test`, `lint`, `fmt`, `types`, `sec`, `check`, `migration "msg"`).

## Qualidade

```bash
ruff check . && ruff format --check . && mypy app && pytest -q && bandit -c pyproject.toml -r app -q && pip-audit
```

### Testes com PostgreSQL

Por padrão os testes rodam em SQLite em memória (rápidos, sem Docker). Os testes marcados com
`@pytest.mark.postgres` precisam de um PostgreSQL real com o schema **migrado pelo Alembic** e só
rodam quando `TEST_DATABASE_URL` está definida; sem ela são *skipped*.

```bash
uv run task db        # sobe o PostgreSQL (docker compose)
DATABASE_URL=postgresql+asyncpg://acai:acai@localhost:5432/acai uv run task migrate
export TEST_DATABASE_URL=postgresql+asyncpg://acai:acai@localhost:5432/acai
uv run pytest -q -m postgres
```

No PowerShell: `$env:TEST_DATABASE_URL = "postgresql+asyncpg://acai:acai@localhost:5432/acai"`.
Cada teste roda numa transação com rollback no final (fixture `pg_session`). O CI sobe o
PostgreSQL 16, roda `alembic upgrade head`, `alembic check` (falha se um model divergir das
migrations) e então os testes.

### Onde colocar cada teste

| Tipo | Pasta | Banco |
|---|---|---|
| Unitário (regra de negócio, sem I/O de rede) | `tests/unit` | SQLite em memória |
| API (rotas, permissões, validação) | `tests/integration` | SQLite em memória |
| Fluxo ponta a ponta (`@pytest.mark.postgres`) | `tests/e2e` | PostgreSQL migrado pelo Alembic |

Os testes são `async` (pytest-asyncio em modo `auto`, cliente `httpx.AsyncClient`; SQLite via `aiosqlite`).

Helpers em `tests/conftest.py`: `auth_headers(email, papel)` cria o usuário, faz login e devolve o
header `Authorization` (use em vez de repetir login nos testes de API); `pg_client` é a API
completa sobre o PostgreSQL. Cada fase nova deve trazer ao menos um fluxo e2e no formato de
`tests/e2e/test_fluxo_usuarios.py`.

## Já incluído
- Login com JWT (access 15 min + refresh), senha em argon2, resposta uniforme contra enumeração
- Papéis (admin, gerente, atendente, caixa) via `require_roles`
- Rate limit de login (em memória; usar Redis com várias réplicas)
- Auditoria (`audit_log`), headers de segurança, CORS por lista, limite de body, docs off em produção
- Unit of Work, Alembic, Docker não-root, CI
- API assíncrona de ponta a ponta: FastAPI + SQLAlchemy `AsyncSession` + `asyncpg` (PostgreSQL). Portas, repositórios,
  Unit of Work e casos de uso são `async`; o hash argon2 roda em thread para não travar o event loop.
  A `DATABASE_URL` usa `postgresql+asyncpg://...` (URLs `postgresql://` ou `+psycopg` são convertidas automaticamente).
  O Alembic também roda via engine assíncrona.
- Gestão de usuários:

  | Rota | Quem | |
  |---|---|---|
  | `GET /usuarios` | admin, gerente | lista paginada (`limit` padrão 20, máx. 100; `offset`) com filtros `ativo`, `papel`, `q` |
  | `GET /usuarios/{id}` | admin, gerente | detalhe |
  | `PATCH /usuarios/{id}` | admin | edita `nome`, `email`, `papel` |
  | `POST /usuarios/{id}/desativar` · `/reativar` | admin | liga/desliga o acesso |
  | `POST /usuarios/{id}/redefinir-senha` | admin | define nova senha de outro usuário |
  | `POST /auth/alterar-senha` | qualquer autenticado | troca a própria senha (exige a atual; com limite de tentativas) |

  Regras: sempre resta ao menos um admin ativo; admin não desativa nem rebaixa a si mesmo;
  e-mail único (minúsculas); toda mutação é auditada só com o diff dos campos, sem senha nem hash.

- Cardápio (`domain/cardapio`): leitura para qualquer usuário autenticado, escrita só admin/gerente.

  | Rota | |
  |---|---|
  | `GET/POST /categorias` · `GET/PATCH /categorias/{id}` | nome único (sem diferenciar maiúsculas) |
  | `GET/POST /tamanhos` · `PATCH /tamanhos/{id}` | variações de venda (300 ml, 500 ml...); use um tamanho "Único" para produtos sem variação |
  | `GET/POST /adicionais` · `PATCH /adicionais/{id}` | nome e preço próprios |
  | `GET/POST /produtos` (filtros `categoria_id`, `ativo`, `q`) · `GET/PATCH /produtos/{id}` | nome único dentro da categoria; a resposta traz `precos` por tamanho |
  | `PUT /produtos/{id}/tamanhos/{tamanho_id}` | define ou reajusta o preço do produto naquele tamanho |
  | `POST /{categorias,tamanhos,adicionais,produtos}/{id}/ativar` · `/desativar` | *soft delete*: item inativo some da venda mas continua referenciável por comandas antigas |

  Preço é `Decimal` no domínio e `Numeric(12,2)` no banco (`CHECK preco >= 0`), nunca `float`; na API
  vai e volta como string (`"18.90"`).
- Estoque (`domain/estoque`): **tudo restrito a admin e gerente**.

  | Rota | |
  |---|---|
  | `GET/POST /estoque/insumos` (filtros `abaixo_do_minimo`, `ativo`, `q`) · `GET/PATCH /estoque/insumos/{id}` | unidade fixa (`g`, `kg`, `ml`, `l`, `un`), sem conversão; o saldo nasce em zero e só muda por movimentação |
  | `POST /estoque/insumos/{id}/ativar` · `/desativar` | |
  | `POST /estoque/insumos/{id}/movimentacoes` | `entrada` soma, `saida` subtrai, `ajuste` define o saldo (`quantidade` = contagem física) |
  | `GET /estoque/insumos/{id}/movimentacoes` | histórico paginado, mais recentes primeiro, filtros `tipo`, `de`, `ate` |
  | `GET /estoque/alertas` | insumos ativos com `estoque_atual <= estoque_minimo` (sem notificação ativa) |
  | `GET/PUT /produtos/{id}/tamanhos/{tamanho_id}/ficha-tecnica` | receita por produto **e** tamanho; o PUT substitui tudo de forma atômica (lista vazia limpa) |
  | `GET/PUT /adicionais/{id}/ficha-tecnica` | receita de um adicional (consumo por porção) |

  Regras: quantidades são `Numeric(12,3)`; o histórico (`movimentacoes_estoque`) é imutável, sem
  update nem delete, e guarda `saldo_antes`/`saldo_apos`; saída que deixaria o saldo negativo
  responde 422 `estoque_insuficiente` e não grava nada; `ajuste` com a contagem igual ao saldo
  é rejeitado (422 `valor_invalido`). Cada movimentação trava o insumo com `SELECT ... FOR UPDATE`
  e grava histórico e saldo na mesma transação, então saídas simultâneas não corrompem o saldo.
  Na ficha, o mesmo insumo não repete na receita e insumo/produto/adicional precisam estar ativos
  e o produto precisa ter preço no tamanho.

  Pontos de reuso (usados pelo fechamento de comanda): `uow.estoque.aplicar_saida(insumo_id,
  quantidade, usuario_id, motivo)` aplica a baixa na transação em andamento (quem chama decide o
  `commit`), `uow.ficha_tecnica.obter_ficha_produto/obter_ficha_adicional` leem as receitas e
  `domain.estoque.regras.calcular_consumo(ficha, quantidade_vendida)` devolve `{insumo_id: quantidade}`.

- Comandas (`domain/comandas`): abrir, lançar itens, fechar com baixa de estoque, cancelar e consultar.
  Abrir, lançar/alterar/remover itens e consultar: **admin, gerente, atendente e caixa**.
  Fechar e cancelar: **admin, gerente e caixa** (o atendente lança, mas não fecha).

  | Rota | |
  |---|---|
  | `POST /comandas` | abre (`cliente_nome` obrigatório; `origem` `balcao`/`whatsapp`, `cliente_contato`, `observacao`) |
  | `GET /comandas` | lista paginada (`limit` 1–100, `offset`) com filtros `status`, `origem`, `cliente` (parcial, sem diferenciar maiúsculas), `aberta_por_id`, `de`/`ate` (por `aberta_em`, inclusivos). Abertas: as mais antigas primeiro; demais: da mais recente para a mais antiga |
  | `GET /comandas/{id}` | detalhe com itens, adicionais, subtotais e total; fechada: inclui `pagamentos` e `troco` |
  | `POST /comandas/{id}/itens` | lança `produto_id`, `tamanho_id`, `quantidade` (1–99), `adicionais: [{adicional_id, quantidade}]`, `observacao`; devolve a comanda |
  | `PATCH /comandas/{id}/itens/{item_id}` | altera `quantidade` e/ou `observacao` (`""` limpa) |
  | `DELETE /comandas/{id}/itens/{item_id}` | remove o item (204) |
  | `POST /comandas/{id}/fechar` | **exige** `{"pagamentos": [...]}` (ver Caixa e pagamentos); fecha baixando o estoque; resposta traz `pagamentos`, `troco`, `sessao_caixa_id`, `consumo` e `itens_sem_ficha` |
  | `POST /comandas/{id}/cancelar` | `aberta → cancelada` (`motivo` opcional vai para a auditoria); não mexe no estoque |

  **Preço congelado:** o preço (`produto_tamanhos.preco`, `adicionais.preco`) e os nomes do produto,
  tamanho e adicionais são copiados para o item no lançamento. Reajustar ou renomear o cardápio
  depois não altera comandas existentes. O mesmo produto/tamanho vira linhas separadas (sem mesclar),
  pois podem ter adicionais e observações diferentes. Subtotal do item =
  `(preço + Σ preço do adicional × qtd) × quantidade`.

  **Fechamento** (`FecharComanda`), tudo na mesma `UnitOfWork` e com um único `commit()`:
  1. trava a comanda (`SELECT ... FOR UPDATE`) e confere `aberta` já com o lock (dois fechamentos
     simultâneos se serializam: o segundo recebe 409); recusa comanda sem itens (409 `comanda_vazia`);
  2. calcula o `total` e valida os pagamentos (validação pura, antes de qualquer outro lock);
  3. se `total > 0`, trava a sessão de caixa aberta (sem ela, 409 `caixa_fechado`);
  4. soma o consumo da ficha técnica da comanda inteira (o mesmo insumo vindo de itens/adicionais
     diferentes é somado) e baixa uma vez por insumo, em **ordem crescente de `insumo_id`**, com
     `motivo = "comanda:<id>"`; falta de **qualquer** insumo desfaz tudo e responde 409
     `estoque_insuficiente` com `insumo_id`, `insumo_nome`, `disponivel` e `solicitado`;
  5. grava os pagamentos vinculados à sessão;
  6. grava `status = fechada`, `fechada_em`, `fechada_por_id` e o `total` (snapshot);
  7. audita total, sessão, formas e valores, troco e consumo por insumo.

  **Ordem global de locks: comanda → sessão de caixa → insumos (ids crescentes).** Lançar, alterar e
  remover itens também travam a comanda antes, então nada muda os itens durante um fechamento.
  `fechada` e `cancelada` são estados terminais (sem estorno nem reabertura). **Produto sem ficha
  técnica** fecha sem baixar estoque e é listado em `itens_sem_ficha` (resposta e auditoria).

  A falta de insumo no fechamento responde **409**; já a movimentação manual de estoque continua **422**.

- Caixa e pagamentos (`domain/caixa`): **admin, gerente e caixa** (o atendente não acessa o caixa).
  Só existe **uma sessão de caixa aberta por vez**, garantido por índice único parcial no banco
  (vale mesmo com duas aberturas simultâneas).

  | Rota | |
  |---|---|
  | `POST /caixa/sessoes` | abre com `valor_abertura` (fundo de troco, >= 0) e `observacao?`; já existe uma aberta: 409 `caixa_ja_aberto` |
  | `GET /caixa/sessoes/atual` | sessão aberta com `saldo_dinheiro`, `resumo_por_forma` e movimentos; 404 `nenhuma_sessao_aberta` |
  | `GET /caixa/sessoes` · `GET /caixa/sessoes/{id}` | listagem paginada (`status`, `de`/`ate` por `aberta_em`) e detalhe |
  | `POST /caixa/sessoes/{id}/movimentos` | `tipo` `sangria` (retirada) ou `suprimento` (reforço), `valor` > 0 e `motivo` obrigatório |
  | `POST /caixa/sessoes/{id}/fechar` | `valor_contado` e `observacao?`; congela `valor_esperado`, `valor_contado` e `diferenca` |

  **Pagamento no fechamento da comanda (contrato novo, incompatível com a Fase 2):**
  `POST /comandas/{id}/fechar` passa a exigir o body

  ```json
  { "pagamentos": [
      { "forma": "dinheiro", "valor": "20.00", "valor_recebido": "50.00" },
      { "forma": "pix", "valor": "20.00" } ] }
  ```

  Formas: `dinheiro`, `pix`, `cartao_debito`, `cartao_credito`. A soma dos `valor` deve ser **exatamente**
  o total da comanda (422 `pagamento_diferente_do_total`), sem forma repetida (`forma_repetida`);
  `valor_recebido` só existe em dinheiro e é `>= valor` (`valor_recebido_invalido`,
  `valor_recebido_insuficiente`); o excedente é o troco. Sem body (ou lista vazia) só fecha comanda de
  total zero, que não exige caixa aberto nem grava pagamento. Sem sessão aberta: 409 `caixa_fechado`
  e a comanda segue aberta. Pagamento, baixa de estoque e status da comanda são uma transação só.

  **Gaveta:** `valor_esperado = abertura + Σ dinheiro (valor aplicado, sem o troco) + suprimentos −
  sangrias`; pix e cartão não entram. Sangria que deixaria o saldo negativo: 409
  `saldo_caixa_insuficiente` (as sangrias travam a sessão, então duas simultâneas se enfileiram).
  Fechar o caixa com `diferenca != 0` exige `observacao` (422 `justificativa_obrigatoria`); comandas
  ainda abertas não impedem o fechamento e serão pagas na próxima sessão. Nunca existe pagamento numa
  sessão fechada: `FecharCaixa` e o fechamento de comanda disputam o lock da sessão, e quem perde vê o
  resultado do outro (o pagamento entra no esperado, ou a comanda recebe 409 `caixa_fechado`).

- Financeiro (`domain/financeiro`): **admin e gerente**. Contas a pagar/receber e despesas; a receita
  de vendas vem dos `pagamentos`, não de lançamentos (o fluxo de caixa do dashboard soma as duas fontes).

  | Rota | |
  |---|---|
  | `GET/POST /financeiro/categorias` · `PATCH /financeiro/categorias/{id}` | `tipo` `receita`/`despesa`; nome único por tipo (sem diferenciar maiúsculas); renomeia, ativa e desativa |
  | `POST /financeiro/lancamentos` | `tipo` `pagar` (categoria de despesa) ou `receber` (receita), `descricao`, `valor` > 0, `vencimento`, `categoria_id`, `contraparte?`, `observacao?`; com `baixa: {data_pagamento, forma}` já nasce pago |
  | `GET /financeiro/lancamentos` | paginada; filtros `tipo`, `status`, `categoria_id`, `atrasados`, `vencimento_de`/`vencimento_ate` (inclusivos), `contraparte` (parcial). Pendentes por vencimento crescente; os demais, do mais recente |
  | `GET/PATCH /financeiro/lancamentos/{id}` | detalhe; edição só de `pendente` |
  | `POST /financeiro/lancamentos/{id}/baixar` · `/cancelar` | `pendente → pago` (`data_pagamento`, `forma`) ou `pendente → cancelado` (`motivo?`); ambos terminais |

  **Atrasado não é status gravado:** a resposta traz `atrasado` (derivado de `pendente` e
  `vencimento < hoje`). "Hoje" é a data no fuso da loja, configurado em `TIMEZONE` (padrão
  `America/Sao_Paulo`).

- Dashboard (`domain/dashboard`, `application/dashboard`): **100% leitura, só admin e gerente**
  (caixa e atendente recebem 403; sem token, 401). Nenhum endpoint grava dado, trava linha ou
  audita. Padrão *query service*: o caso de uso valida permissão e período e chama a porta
  `DashboardQueries`; o SQL só filtra, agrupa e soma (`GROUP BY`), e as contas (ticket médio,
  variação, série preenchida, acumulado, cobertura) são funções puras em `domain/dashboard`.

  | Rota (`GET`) | Parâmetros | Resposta |
  |---|---|---|
  | `/dashboard/visao-geral` | – | vendas de hoje vs. mesmo dia da semana anterior, comandas abertas, caixa (saldo em dinheiro em tempo real), contadores de estoque e contas atrasadas |
  | `/dashboard/vendas/resumo` | `de`, `ate` | faturamento, qtd de comandas, ticket médio, itens vendidos, canceladas (informativo) + período anterior e `variacao_pct` |
  | `/dashboard/vendas/serie` | `de`, `ate`, `agrupamento` (`dia`\|`semana`\|`mes`) | uma posição por bucket, com zeros onde não houve venda |
  | `/dashboard/vendas/mais-vendidos` | `de`, `ate`, `limite` (1–50), `ordenar_por` (`quantidade`\|`receita`) | ranking por produto com `participacao_pct` |
  | `/dashboard/vendas/por-forma-pagamento` | `de`, `ate` | as quatro formas sempre presentes (`0.00` se não houve) |
  | `/dashboard/vendas/por-hora` | `de`, `ate` | 24 posições (hora local) |
  | `/dashboard/estoque/critico` | `nivel` (`zerado`\|`critico`), `limit`, `offset` | insumos críticos + `total_zerados`/`total_criticos` |
  | `/dashboard/financeiro/fluxo-caixa` | `de`, `ate`, `agrupamento`, `incluir_projecao` | realizado por bucket, resultado, saídas por categoria e, opcional, projeção |
  | `/dashboard/financeiro/contas` | – | posição de pagar/receber de hoje e os 10 próximos vencimentos |

  **Período e fuso.** `de`/`ate` são datas **inclusivas** no fuso `TIMEZONE`. Padrão: últimos 30
  dias até hoje. A consulta usa `[de 00:00 local, ate+1 00:00 local)` convertido para UTC, então uma
  venda às 23:30 de São Paulo (02:30 UTC do dia seguinte) pertence ao dia local. 422
  `periodo_invalido` (o campo `motivo` diz qual): `periodo_invertido`, `periodo_no_futuro`,
  `periodo_longo_demais` (> 366 dias) e `agrupamento_dia_longo_demais` (`dia` só até 92 dias). Só o
  fluxo com `incluir_projecao=true` aceita `ate` no futuro. Período sem venda é 200 com zeros. O
  período anterior tem a mesma duração e vem logo antes. Semana começa na **segunda**; mês é o
  mês-calendário; os buckets das pontas trazem `inicio`/`fim` recortados ao período pedido.

  **O que é venda.** Comanda `fechada`, datada por `fechada_em`, somando o `total` gravado no
  fechamento; nome e preço dos itens vêm do snapshot da comanda (renomear ou reprecificar o produto
  não muda o histórico). `aberta` nunca entra; `cancelada` só aparece em `comandas_canceladas`
  (contada pela data do `cancelar` no `audit_log`, já que a comanda não guarda a data do
  cancelamento). Receita do item = `quantidade × (preço + Σ adicionais)`. Invariante testada, no
  mesmo período: `Σ série == resumo.faturamento == Σ por forma == Σ receita dos itens`.

  **Variação e percentuais.** `variacao_pct` tem 1 casa e é `null` quando o anterior é zero. Dinheiro
  é sempre `Decimal` com 2 casas (string no JSON); percentuais são `Decimal` no cálculo e número no
  JSON. Cada participação é arredondada sozinha, então a soma pode diferir de 100 em até 0,1 por linha.

  **Fluxo de caixa (regime de caixa).** `entradas_vendas` = `pagamentos` das comandas fechadas (todas
  as formas, não só a gaveta); `entradas_outras` = lançamentos `receber` pagos e `saidas` = `pagar`
  pagos, ambos por `data_pagamento`. Sem contagem dupla (venda não gera lançamento). Pendente e
  cancelado nunca entram no realizado; sangria, suprimento e fundo de troco também não. O
  `saldo_acumulado` corre desde o início do período (não há saldo anterior). A projeção (pendentes por
  `vencimento`) vem separada e nunca é somada ao realizado. O resultado é de caixa, **não é lucro**:
  o sistema ainda não guarda custo de insumo.

  **Estoque crítico.** Insumo ativo, com `estoque_minimo > 0` e `estoque_atual <= estoque_minimo`
  (exatamente no mínimo conta). Ordem: zerados, menor `cobertura_pct`, nome. Ordenação e paginação
  são em memória sobre uma única consulta (o conjunto é limitado pelos insumos cadastrados), então os
  contadores valem para todos os críticos, mesmo com `nivel` ou página fora do alcance.

  **Consistência de leitura.** Uma sessão por requisição, `READ COMMITTED`, sem lock: duas consultas
  da mesma resposta podem enxergar instantes ligeiramente diferentes, o que é aceitável para um
  dashboard. Nada de cache. Na visão geral, qualquer falha devolve 500 para a resposta toda (nunca um
  número faltando ou zerado por engano).

  **Desempenho.** Número fixo de consultas por endpoint, independente do volume: 1 em todos, exceto
  `contas` (2: posição + próximos vencimentos) e `visao-geral` (5, reaproveitando as mesmas
  consultas). A migration `0009_dashboard_indices` só cria índices: parcial `comandas (fechada_em)
  WHERE status = 'fechada'`, `itens_comanda (comanda_id, produto_id)` e `lancamentos (status,
  data_pagamento)`. Nos testes com PostgreSQL, as consultas de vendas usam o índice parcial (sem
  `Seq Scan` em `comandas`). Lucro, margem, exportação e cache ficam fora desta fase.

Erros (formato `{code, detail}`): `categoria_nao_encontrada`, `produto_nao_encontrado`,
`tamanho_nao_encontrado`, `adicional_nao_encontrado`, `insumo_nao_encontrado`,
`comanda_nao_encontrada`, `item_comanda_nao_encontrado` (404); `nome_ja_cadastrado`,
`comanda_nao_aberta`, `comanda_vazia`, `estoque_insuficiente` no fechamento (409);
`estoque_insuficiente` na movimentação manual, `ficha_tecnica_invalida`, `valor_invalido` e, nos itens
da comanda, `produto_inativo`, `tamanho_inativo`, `adicional_inativo`, `produto_sem_preco`,
`adicional_repetido` (422). Caixa e financeiro: 404 `sessao_caixa_nao_encontrada`,
`nenhuma_sessao_aberta`, `categoria_financeira_nao_encontrada`, `lancamento_nao_encontrado`; 409
`caixa_ja_aberto`, `caixa_fechado`, `sessao_nao_aberta`, `saldo_caixa_insuficiente`,
`lancamento_nao_pendente`, `categoria_financeira_inativa`; 422 `pagamento_diferente_do_total`,
`forma_repetida`, `valor_recebido_invalido`, `valor_recebido_insuficiente`,
`justificativa_obrigatoria`, `categoria_incompativel`, `valor_invalido`; dashboard: 422
`periodo_invalido` (com `motivo`). Toda escrita é auditada
(`criar`, `atualizar`, `ativar`/`desativar`, `definir_preco`, `movimentar`, `definir_ficha`, `abrir`,
`adicionar_item`, `atualizar_item`, `remover_item`, `fechar`, `cancelar`, `sangria`, `suprimento`,
`baixar`).

### Limitação conhecida: senha e refresh token

Enquanto a revogação de refresh token não existir (Fase 6), **trocar ou redefinir a senha não
invalida os tokens já emitidos**: o access vale até 15 min e o refresh até 7 dias. Já **desativar o
usuário corta o acesso na hora**, porque `ativo` é checado a cada requisição (e no refresh).

## Próximos passos
1. Múltiplos caixas/terminais simultâneos
2. Bot WhatsApp + Gemini atrás de portas em `application/ports/` — validar assinatura do webhook,
   idempotência pelo ID da mensagem, LLM só devolve JSON validado contra cardápio/preços reais
3. Revogação de refresh token (jti em banco/Redis)
4. Estorno, reabertura e cancelamento de comanda fechada (exigem devolver estoque e pagamento)
