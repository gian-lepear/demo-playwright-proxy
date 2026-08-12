"""O conserto: um handler CDP só, que autentica e bloqueia.

Duas formas de acertar, e a escolha depende de quem sobe o browser.

    uv run python 03_cdp.py

Precisa do proxy no ar: `just up`.
"""

import time

from playwright.sync_api import sync_playwright

from comum import (
    ALVO,
    BLOQUEADOS_CDP,
    BLOQUEADOS_ROUTE,
    PROXY,
    PROXY_SENHA,
    PROXY_USUARIO,
    Medicao,
    bytes_no_proxy,
    contar_bytes,
    exigir_proxy,
    imprimir,
)


def pela_api() -> Medicao:
    """Quando você mesmo sobe o browser, não precisa de CDP nenhum.

    `launch(proxy=...)` trata o 407 sozinho e não atrapalha o `context.route`.
    Muita gente desce pro CDP sem saber que esta opção existe.
    """
    medicao = Medicao(rotulo="A) API do Playwright, sem CDP")
    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY)
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


def pelo_cdp() -> Medicao:
    """Quando o browser não é seu: Browserless, container remoto, pool.

    Aí `launch(proxy=...)` não existe e autenticar exige CDP. A regra é: se você
    liga `Fetch.enable`, passa a ser dono das DUAS coisas, autenticação e
    interceptação. Não são duas features, é uma.
    """
    medicao = Medicao(rotulo="B) handler CDP único")
    with sync_playwright() as p:
        navegador = p.chromium.launch(proxy=PROXY)
        contexto = navegador.new_context()
        pagina = contexto.new_page()
        cdp = contexto.new_cdp_session(pagina)
        contar_bytes(cdp, medicao)

        # `handleAuthRequests` é o que separa isto do script 02.
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
            # Capitalizado aqui, minúsculo no `route` do `pela_api` acima.
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
    exigir_proxy()
    for fn in (pela_api, pelo_cdp):
        antes = time.time()
        medicao = fn()
        imprimir(medicao, proxy=bytes_no_proxy(desde=antes))
    print()
