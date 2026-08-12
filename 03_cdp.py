"""O conserto: um handler CDP só, que autentica e bloqueia.

Duas formas de acertar, e a escolha depende de quem sobe o browser.

    uv run python 03_cdp.py

Precisa do proxy no ar: `just up`.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_CDP,
    BLOQUEADOS_ROUTE,
    PROXY_HOST,
    PROXY_PORTA,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    bytes_no_proxy,
    contar_bytes,
    imprimir,
)

PROXY_PLAYWRIGHT = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORTA}",
    "username": PROXY_USUARIO,
    "password": PROXY_SENHA,
}


def pela_api(rotulo: str = "A) API do Playwright, sem CDP") -> Medicao:
    """Quando você mesmo sobe o browser, não precisa de CDP nenhum.

    `launch(proxy=...)` trata o 407 sozinho e não atrapalha o `context.route`.
    É a opção mais simples, e muita gente vai direto pro CDP sem saber que ela
    existe.
    """
    medicao = Medicao(rotulo=rotulo)
    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY_PLAYWRIGHT)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        contar_bytes(contexto.new_cdp_session(pagina), medicao)

        def filtrar(rota, requisicao):
            if requisicao.resource_type in BLOQUEADOS_ROUTE:
                medicao.bloqueadas += 1
                rota.abort()
            else:
                rota.continue_()

        contexto.route("**/*", filtrar)
        pagina.goto(ALVO, wait_until="networkidle")
        navegador.close()
    return medicao


def pelo_cdp(rotulo: str = "B) handler CDP único") -> Medicao:
    """Quando o browser não é seu: Browserless, container remoto, pool.

    Aí `launch(proxy=...)` não existe, e autenticar exige CDP. A regra é: se
    você liga `Fetch.enable`, passa a ser dono das DUAS coisas, autenticação e
    interceptação. Não são duas features, é uma.
    """
    medicao = Medicao(rotulo=rotulo)
    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY_PLAYWRIGHT)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        contar_bytes(cdp, medicao)

        # `handleAuthRequests` é o que separa isto do script 02. Sem ele o
        # desafio do proxy chega e ninguém responde.
        cdp.send("Fetch.enable", {"handleAuthRequests": True, "patterns": [{"urlPattern": "*"}]})

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

        def pausada(evento):
            # ATENÇÃO: aqui o tipo vem capitalizado (`Image`), e no `route` do
            # Playwright vem minúsculo (`image`). Copiar o set do outro script
            # produz um filtro que nunca casa, não dá erro, e a página carrega
            # inteira parecendo que o bloqueio funciona.
            if evento.get("resourceType") in BLOQUEADOS_CDP:
                medicao.bloqueadas += 1
                cdp.send(
                    "Fetch.failRequest",
                    {"requestId": evento["requestId"], "errorReason": "BlockedByClient"},
                )
            else:
                cdp.send("Fetch.continueRequest", {"requestId": evento["requestId"]})

        cdp.on("Fetch.requestPaused", pausada)

        pagina.goto(ALVO, wait_until="networkidle")
        navegador.close()
    return medicao


if __name__ == "__main__":
    for fn in (pela_api, pelo_cdp):
        antes = __import__("time").time()
        medicao = fn()
        imprimir(medicao, proxy=bytes_no_proxy(desde=antes))
    print()
