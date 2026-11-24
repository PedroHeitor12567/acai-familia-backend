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
DATABASE_URL=postgresql+psycopg://acai:acai@localhost:5432/acai uv run task migrate
export TEST_DATABASE_URL=postgresql+psycopg://acai:acai@localhost:5432/acai
uv run pytest -q -m postgres
```

No PowerShell: `$env:TEST_DATABASE_URL = "postgresql+psycopg://acai:acai@localhost:5432/acai"`.
Cada teste roda numa transação com rollback no final (fixture `pg_session`). O CI sobe o
PostgreSQL 16, roda `alembic upgrade head`, `alembic check` (falha se um model divergir das
migrations) e então os testes.

## Já incluído
- Login com JWT (access 15 min + refresh), senha em argon2, resposta uniforme contra enumeração
- Papéis (admin, gerente, atendente, caixa) via `require_roles`
- Rate limit de login (em memória; usar Redis com várias réplicas)
- Auditoria (`audit_log`), headers de segurança, CORS por lista, limite de body, docs off em produção
- Unit of Work, Alembic, Docker não-root, CI
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

### Limitação conhecida: senha e refresh token

Enquanto a revogação de refresh token não existir (Fase 6), **trocar ou redefinir a senha não
invalida os tokens já emitidos**: o access vale até 15 min e o refresh até 7 dias. Já **desativar o
usuário corta o acesso na hora**, porque `ativo` é checado a cada requisição (e no refresh).

## Próximos passos
1. Cardápio, estoque e comandas (transações + `SELECT ... FOR UPDATE` na baixa de estoque)
2. Caixa e financeiro (`Numeric(12,2)`, nunca float)
3. Dashboard (consultas de leitura)
4. Bot WhatsApp + Gemini atrás de portas em `application/ports/` — validar assinatura do webhook,
   idempotência pelo ID da mensagem, LLM só devolve JSON validado contra cardápio/preços reais
5. Revogação de refresh token (jti em banco/Redis)
