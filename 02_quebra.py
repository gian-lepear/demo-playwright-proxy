"""As três formas de quebrar, todas em silêncio ou com erro que não explica nada.

    uv run python 02_quebra.py

Precisa do proxy no ar: `just up`.
"""

from __future__ import annotations

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_ROUTE,
    PROXY_HOST,
    PROXY_PORTA,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    contar_bytes,
)

PROXY_PLAYWRIGHT = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORTA}",
    "username": PROXY_USUARIO,
    "password": PROXY_SENHA,
}


def um_credencial_na_url() -> None:
    """A tentativa óbvia, e a flag do Chrome simplesmente ignora a credencial."""
    print("\n1. credencial embutida em --proxy-server")
    url = f"http://{PROXY_USUARIO}:{PROXY_SENHA}@{PROXY_HOST}:{PROXY_PORTA}"
    print(f"   --proxy-server={url}")
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=[f"--proxy-server={url}"])
        pagina = navegador.new_page()
        try:
            pagina.goto(ALVO, wait_until="domcontentloaded", timeout=20000)
            print("   carregou (não deveria)")
        except ErroPlaywright as erro:
            print(f"   {str(erro).splitlines()[0][:90]}")
        navegador.close()
    print("   A flag aceita só host:porta. Credencial na URL não é lida, e o erro")
    print("   fala de proxy não suportado, não de autenticação.")


def dois_sem_credencial() -> None:
    """Sem credencial o desafio 407 chega e ninguém responde."""
    print("\n2. --proxy-server sem credencial")
    with sync_playwright() as p:
        navegador = p.chromium.launch(args=[f"--proxy-server=http://{PROXY_HOST}:{PROXY_PORTA}"])
        pagina = navegador.new_page()
        try:
            pagina.goto(ALVO, wait_until="domcontentloaded", timeout=15000)
            print("   carregou (não deveria)")
        except ErroPlaywright as erro:
            print(f"   {str(erro).splitlines()[0][:90]}")
        navegador.close()
    print("   Trava até o timeout. O 407 do proxy nunca é respondido.")


def tres_fetch_sem_auth() -> Medicao:
    """A armadilha de verdade, e a única que não dá erro nenhum.

    Ligar `Fetch.enable` sem `handleAuthRequests` tira do Playwright o desafio de
    autenticação. Ele passa a chegar em você, e você não está escutando.
    """
    print("\n3. Fetch.enable sem handleAuthRequests, junto do context.route")
    medicao = Medicao(rotulo="quebrado")

    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY_PLAYWRIGHT)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        contar_bytes(cdp, medicao)

        # Faltou `"handleAuthRequests": True`. É só isso.
        cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        cdp.on(
            "Fetch.requestPaused",
            lambda e: cdp.send("Fetch.continueRequest", {"requestId": e["requestId"]}),
        )

        def filtrar(rota, requisicao):
            if requisicao.resource_type in BLOQUEADOS_ROUTE:
                medicao.bloqueadas += 1
                rota.abort()
            else:
                rota.continue_()

        contexto.route("**/*", filtrar)

        try:
            pagina.goto(ALVO, wait_until="networkidle", timeout=25000)
            print("   goto retornou SEM erro")
        except ErroPlaywright as erro:
            print(f"   {str(erro).splitlines()[0][:90]}")
        navegador.close()

    print(f"   requisições concluídas: {medicao.requisicoes}")
    print(f"   bytes: {medicao.bytes_rede}")
    print("   Nenhuma exceção, nenhum log, nenhuma requisição. `networkidle`")
    print("   resolve na hora justamente porque nada aconteceu.")
    return medicao


if __name__ == "__main__":
    um_credencial_na_url()
    dois_sem_credencial()
    tres_fetch_sem_auth()
    print("\nO conserto de todos está no 03_cdp.py\n")
