# Sobe o proxy autenticado local. Precisa de docker.
up:
    docker compose up -d
    @echo "proxy em localhost:3128, usuario demo, senha demo123"

down:
    docker compose down

# A solucao conhecida, sem proxy nenhum.
ingenuo:
    uv run python 01_ingenuo.py

# As tres formas de quebrar quando entra proxy autenticado.
quebra:
    uv run python 02_quebra.py

# O conserto, nas duas formas.
cdp:
    uv run python 03_cdp.py

# A tabela final.
medir:
    uv run python medir.py

# Tudo, na ordem do post.
tudo: up ingenuo quebra cdp medir

fmt:
    uv run ruff format . && uv run ruff check --fix .

lint:
    uv run ruff check .
