"""As formas de quebrar, todas em silêncio ou com erro que não explica nada.

    uv run python 02_quebra.py

Precisa do proxy no ar: `just up`.
"""

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_ROUTE,
    PROXY,
    PROXY_HOST,
    PROXY_PORTA,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    contar_bytes,
    exigir_proxy,
)


def primeira_linha(erro: ErroPlaywright) -> str:
    return str(erro).splitlines()[0][:90]


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
            print(f"   {primeira_linha(erro)}")
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
            print(f"   {primeira_linha(erro)}")
        navegador.close()
    print("   Trava até o timeout. O 407 do proxy nunca é respondido.")


def tres_fetch(com_auth: bool) -> Medicao:
    """`Fetch.enable` junto do `context.route`, com e sem `handleAuthRequests`.

    O A/B é o que derruba a explicação corrente. A dupla não briga: sem
    `handleAuthRequests` o desafio de autenticação chega em você e ninguém
    responde, e é só isso.
    """
    com, sem = ("com", "3b") if com_auth else ("sem", "3")
    print(f"\n{sem}. Fetch.enable {com} handleAuthRequests, junto do context.route")
    medicao = Medicao(rotulo=f"fetch {com} auth")

    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        contar_bytes(cdp, medicao)

        opcoes = {"patterns": [{"urlPattern": "*"}]}
        if com_auth:
            opcoes["handleAuthRequests"] = True
            cdp.on(
                "Fetch.authRequired",
                lambda e: cdp.send(
                    "Fetch.continueWithAuth",
                    {
                        "requestId": e["requestId"],
                        "authChallengeResponse": {
                            "response": "ProvideCredentials",
                            "username": PROXY_USUARIO,
                            "password": PROXY_SENHA,
                        },
                    },
                ),
            )

        cdp.send("Fetch.enable", opcoes)
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
            print(f"   {primeira_linha(erro)}")
        navegador.close()

    print(f"   requisições concluídas: {medicao.requisicoes}, bloqueadas: {medicao.bloqueadas}")
    if not com_auth:
        print("   Nenhuma exceção, nenhum log, nenhuma requisição. `networkidle`")
        print("   resolve na hora justamente porque nada aconteceu.")
    return medicao


if __name__ == "__main__":
    exigir_proxy()
    um_credencial_na_url()
    dois_sem_credencial()
    sem_auth = tres_fetch(com_auth=False)
    com_auth = tres_fetch(com_auth=True)

    print(f"\n   sem handleAuthRequests: {sem_auth.requisicoes} concluídas")
    print(
        f"   com handleAuthRequests: {com_auth.requisicoes} concluídas,"
        f" {com_auth.bloqueadas} bloqueadas"
    )
    print("   Não brigam pelo mesmo mecanismo. Faltava responder o desafio.")
    print("\nO conserto de todos está no 03_cdp.py\n")
