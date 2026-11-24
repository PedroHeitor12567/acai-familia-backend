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

## Já incluído
- Login com JWT (access 15 min + refresh), senha em argon2, resposta uniforme contra enumeração
- Papéis (admin, gerente, atendente, caixa) via `require_roles`
- Rate limit de login (em memória; usar Redis com várias réplicas)
- Auditoria (`audit_log`), headers de segurança, CORS por lista, limite de body, docs off em produção
- Unit of Work, Alembic, Docker não-root, CI

## Próximos passos
1. Cardápio, estoque e comandas (transações + `SELECT ... FOR UPDATE` na baixa de estoque)
2. Caixa e financeiro (`Numeric(12,2)`, nunca float)
3. Dashboard (consultas de leitura)
4. Bot WhatsApp + Gemini atrás de portas em `application/ports/` — validar assinatura do webhook,
   idempotência pelo ID da mensagem, LLM só devolve JSON validado contra cardápio/preços reais
5. Revogação de refresh token (jti em banco/Redis)
