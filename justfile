# Dependências e o browser do Playwright. O `uv sync` sozinho não baixa o Chromium.
instalar:
    uv sync
    uv run playwright install chromium

# Sobe o proxy autenticado local e espera ele responder 407. Precisa de docker.
up:
    docker compose up -d --wait
    @echo "proxy em localhost:3128, usuário demo, senha demo123"

down:
    docker compose down

# A solução conhecida, sem proxy nenhum.
ingenuo:
    uv run python 01_ingenuo.py

# As formas de quebrar quando entra proxy autenticado.
quebra:
    uv run python 02_quebra.py

# O conserto, nas duas formas.
cdp:
    uv run python 03_cdp.py

medir:
    uv run python medir.py

tudo: instalar up ingenuo quebra cdp medir

fmt:
    uv run ruff format . && uv run ruff check --fix .

lint:
    uv run ruff check .
