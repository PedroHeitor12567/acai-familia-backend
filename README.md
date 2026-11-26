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

  **Para a Fase 2 (comandas):** `uow.estoque.aplicar_saida(insumo_id, quantidade, usuario_id, motivo)`
  aplica a baixa na transação em andamento (quem chama decide o `commit`),
  `uow.ficha_tecnica.obter_ficha_produto/obter_ficha_adicional` leem as receitas e
  `domain.estoque.regras.calcular_consumo(ficha, quantidade_vendida)` devolve `{insumo_id: quantidade}`.

Erros novos (formato `{code, detail}`): `categoria_nao_encontrada`, `produto_nao_encontrado`,
`tamanho_nao_encontrado`, `adicional_nao_encontrado`, `insumo_nao_encontrado` (404);
`nome_ja_cadastrado` (409); `estoque_insuficiente`, `ficha_tecnica_invalida`, `valor_invalido` (422).
Toda escrita é auditada (`criar`, `atualizar`, `ativar`/`desativar`, `definir_preco`, `movimentar`,
`definir_ficha`).

### Limitação conhecida: senha e refresh token

Enquanto a revogação de refresh token não existir (Fase 6), **trocar ou redefinir a senha não
invalida os tokens já emitidos**: o access vale até 15 min e o refresh até 7 dias. Já **desativar o
usuário corta o acesso na hora**, porque `ativo` é checado a cada requisição (e no refresh).

## Próximos passos
1. Comandas (consomem cardápio, preços e baixa de estoque; transação única no fechamento)
2. Caixa e financeiro (`Numeric(12,2)`, nunca float)
3. Dashboard (consultas de leitura)
4. Bot WhatsApp + Gemini atrás de portas em `application/ports/` — validar assinatura do webhook,
   idempotência pelo ID da mensagem, LLM só devolve JSON validado contra cardápio/preços reais
5. Revogação de refresh token (jti em banco/Redis)
