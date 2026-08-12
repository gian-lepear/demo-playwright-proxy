# Bloqueio de assets no Playwright com proxy autenticado na frente

Demo reproduzível do post _Bloquear assets no Playwright é fácil. Com proxy
autenticado, não_. Roda na sua máquina, sem pagar nada.

## Por que existe

Proxy residencial cobra por gigabyte. Bloquear imagem, fonte e CSS que o parser
não lê é dinheiro direto. O truque é conhecido.

O que ninguém escreve é o que acontece no dia em que entra um proxy autenticado
na frente. Este repo reproduz as falhas e mede as duas soluções.

**Nada aqui custa dinheiro.** O que quebra o Chrome não é o IP residencial, é a
autenticação, e isso um Squid local reproduz idêntico. O que não é reproduzido,
porque não muda o resultado: rotação de IP, geolocalização e a cobrança por GB.

Mas o Squid registra os bytes de cada conexão, que é **a mesma grandeza que o
fornecedor factura**. Você vê o número que pagaria, sem pagar.

## Rodar

Precisa de [docker](https://docs.docker.com/engine/install/),
[uv](https://docs.astral.sh/uv/) e [just](https://github.com/casey/just).

```sh
just instalar # dependências e o Chromium do Playwright
just up       # sobe o proxy autenticado local
just tudo     # roda os quatro scripts na ordem do post
just down
```

Em Linux enxuto o Chromium ainda pode faltar biblioteca de sistema, e o erro
sai como `error while loading shared libraries`. Nesse caso rode
`uv run playwright install-deps chromium`, que pede sudo.

Ou um de cada vez:

```sh
just ingenuo  # a solução conhecida, sem proxy
just quebra   # as formas de quebrar
just cdp      # o conserto, nas duas formas
just medir    # a tabela
```

## O que cada script mostra

### `01_ingenuo.py`

`context.route` com `abort()`. Funciona, e se o seu caso é esse, pare aqui.

```
baseline              30 req    329.2 KiB
com bloqueio           6 req     74.5 KiB    -77.4%
```

### `02_quebra.py`

As formas de quebrar. As duas primeiras dão erro, a terceira não dá nada.

**Credencial embutida na flag.** `--proxy-server=http://usuario:senha@host:porta`
morre com `ERR_NO_SUPPORTED_PROXIES`. A flag aceita só `host:porta`, e o erro
fala de proxy não suportado, não de autenticação.

**Sem credencial.** Trava até o timeout. O `407` chega e ninguém responde.

**`Fetch.enable` sem `handleAuthRequests`.** Esta é a que morde. Ao ligar o
`Fetch`, você passa a receber o desafio de autenticação do proxy. Se não estiver
escutando `Fetch.authRequired`, ele fica sem resposta:

```
goto retornou SEM erro
requisições concluídas: 0, bloqueadas: 0
```

Nenhuma exceção. Nenhum log. `networkidle` resolve na hora, justamente porque
nada aconteceu.

O script roda o mesmo cenário de novo **com** `handleAuthRequests` e imprime o
A/B. Os dois entregam 6 requisições e 23 bloqueadas, ou seja `Fetch.enable` e
`context.route` convivem. A briga entre eles é a explicação que circula, e ela
está errada. O que faltava era responder o desafio.

### `03_cdp.py`

Duas formas de acertar, e a escolha depende de quem sobe o browser.

**`launch(proxy=...)`**, quando o browser é seu. O Playwright trata o `407`
sozinho e **não** atrapalha o `context.route`. É a opção simples, e muita gente
vai direto pro CDP sem saber que ela existe.

**Handler CDP único**, quando o browser não é seu: Browserless, container
remoto, pool compartilhado. Aí `launch(proxy=...)` não existe. A regra é: se você
liga `Fetch.enable`, passa a ser dono das **duas** coisas, autenticação e
interceptação. Não são duas features, é uma.

> O CDP usa tipo capitalizado (`Image`, `Stylesheet`, `Font`, `Media`). O `route`
> do Playwright usa minúsculo. Copiar o set de um pro outro produz um filtro que
> nunca casa, não dá erro, e a página carrega inteira parecendo que o bloqueio
> funciona.

### `medir.py`

A tabela, com os dois lados da conta.

```
| Cenário           | Requisições | Banda (KiB) | Delta  |
| baseline          |          30 |       329.1 | -      |
| só bloqueio       |           6 |        74.4 | -77.4% |
| bloqueio + bypass |           6 |        74.5 | -77.4% |

| Cenário           | Faturado pelo proxy (KiB) | Delta   |
| baseline          |                     346.3 | -       |
| só bloqueio       |                      84.4 | -75.6%  |
| bloqueio + bypass |                       0.0 | -100.0% |
```

Repare que **o lado cliente é idêntico nos dois últimos**, e o faturado vai a
zero. É o segundo eixo do post: bloquear e tirar do proxy são perguntas
diferentes.

Por requisição são duas decisões independentes:

1. A página precisa disso?
2. Se precisa, precisa sair pelo **meu** IP?

A terceira combinação, carrega mas sai `DIRECT` via `--proxy-bypass-list`, é a
que quase ninguém usa.

Ressalva honesta: `books.toscrape.com` não carrega um único domínio de terceiro,
então aqui o demo tira o próprio alvo do proxy pra mostrar o mecanismo. Num alvo
real você listaria o CDN de estáticos, o analytics e a fonte hospedada fora.

## Três armadilhas do Squid que custaram tempo

Se você for adaptar o `squid.conf`, as três falham sem dizer por quê.

**`max_filedescriptors 1024` é obrigatório.** Sem ela o Squid dimensiona
estruturas pelo `RLIMIT_NOFILE` do container, que no Docker é enorme, e aborta
com `xcalloc: Unable to allocate 1073741816 blocks`. A mensagem não menciona
descritor de arquivo. A imagem oficial carrega essa linha num `include` que some
quando você troca o `squid.conf` inteiro.

**`credentialsttl 0 seconds` derruba o Squid com segfault** no primeiro CONNECT
autenticado. É justamente a diretiva que parece certa pra garantir que o desafio
aconteça sempre.

**A ordem do `http_access` decide.** A primeira regra que casa vence, então
`http_access allow autenticado` antes de `deny CONNECT !SSL_ports` transforma a
segunda em enfeite: qualquer usuário autenticado abre túnel pra qualquer porta,
e nada no log avisa.

## Medição

Os números do lado cliente vêm de `Network.loadingFinished.encodedDataLength`,
que é byte real na rede, já comprimido. Somar `len(response.body())` mediria o
conteúdo descomprimido e infla o número.

Os do lado proxy vêm da coluna `%<st` do `access.log` do Squid, que é o que o
proxy entregou ao cliente naquela transação.

O Squid só escreve a linha do `CONNECT` **quando o túnel fecha**, e o túnel fecha
no `browser.close()`. Ler o log na hora pega o túnel da execução anterior, e dois
cenários seguidos saem com os números trocados.

## Alvo

[books.toscrape.com](https://books.toscrape.com/), que existe para treino de
scraping. Sem questão legal e sem revelar nada de trabalho de ninguém.
