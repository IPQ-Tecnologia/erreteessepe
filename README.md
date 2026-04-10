# RTSP para WebRTC com MediaMTX, FastAPI e Keycloak

## Visão geral

Esta aplicação expõe câmeras RTSP como streams WebRTC sob demanda, com controle de acesso por papéis e autenticação integrada ao Keycloak.

O stack principal é:

- `FastAPI` para autenticação, autorização, preparação do stream e proxy WHEP.
- `MediaMTX` para ingestão RTSP e entrega WebRTC/WHEP.
- `Redis` para sessão HTTP e catálogo de câmeras.

## Contexto da aplicação

O fluxo principal é:

1. O usuário autentica no Keycloak.
2. A API valida o token e verifica se o usuário tem acesso à câmera solicitada.
3. A API resolve a câmera a partir do Redis e, se necessário, do fallback estático em `api/app/domain/cameras.py`.
4. A API verifica se a fonte RTSP responde, cria a rota no MediaMTX e espera o stream ficar pronto.
5. O frontend abre uma sessão WHEP/WebRTC e exibe o vídeo em `/player`.

Pontos de entrada úteis:

- `http://localhost:8000/`: tela de login.
- `http://localhost:8000/player`: player WebRTC.
- `http://localhost:8000/docs`: documentação OpenAPI da API.
- `http://localhost:9997/v3/paths/list`: API do MediaMTX.

## Arquitetura resumida

- `api/app/api/routes.py`: rotas HTTP da aplicação.
- `api/app/usecases/prepare_stream.py`: regra de negócio de preparação do stream.
- `api/app/infrastructure/mediamtx_client.py`: integração com a API do MediaMTX.
- `api/app/infrastructure/whep_proxy.py`: proxy WHEP entre browser/API/MediaMTX.
- `api/app/infrastructure/camera_catalog.py`: leitura do catálogo de câmeras em Redis e fallback local.
- `mediamtx/mediamtx.yml`: configuração-base do MediaMTX.
- `docker-compose.yaml`: stack principal.
- `docker-compose.turn.yaml`: overlay opcional com TURN.

## Pré-requisitos


### macOS

Observação importante para macOS:

- Se você for usar o overlay TURN, `TURN_PUBLIC_IP` deve ser o IP da interface de rede da sua máquina na LAN, não `localhost`.

### Execução local da API sem container

Se quiser rodar apenas a API localmente, além do Docker para Redis/MediaMTX você precisa de:

- Python 3.11+
- `ffmpeg`/`ffprobe` instalados no host

Instalação típica:

- Linux Debian/Ubuntu: `sudo apt-get install -y ffmpeg`
- Linux Fedora: `sudo dnf install -y ffmpeg`
- macOS com Homebrew: `brew install ffmpeg`

## Variáveis de ambiente

O projeto usa `.env` na execução com Docker. Um modelo inicial está em [`.env.example`](./.env.example).

### Modo de autenticação e entrega

| Variável | Padrão | Uso |
| --- | --- | --- |
| `AUTH_PROVIDER` | `keycloak` | Define o provedor de autenticação da aplicação. O modo atual esperado é `keycloak`. |
| `MEDIA_AUTH_MODE` | `internal_jwt` | Define como a API autentica no MediaMTX. O valor recomendado é `internal_jwt`. |

### Credenciais para API do MediaMTX

| Variável | Padrão | Uso |
| --- | --- | --- |
| `MEDIAMTX_API_USER` | `backend` | Usuário usado quando a API precisa autenticar no MediaMTX por usuário/senha ou por token emitido pelo Keycloak. |
| `MEDIAMTX_API_PASS` | `backendpassword` | Senha correspondente ao usuário acima. |

### Catálogo de câmeras e Redis

| Variável | Padrão | Uso |
| --- | --- | --- |
| `CAMERA_REDIS_URL` | `redis://redis:6379/0` | URL do Redis que armazena o catálogo de câmeras e sessões. Em execução local fora do Docker, normalmente vira `redis://localhost:6379/0`. |
| `CAMERA_REDIS_PREFIX` | `camera:` | Prefixo das chaves de câmeras no Redis. |
| `CAMERA_REDIS_TIMEOUT_SECONDS` | `2` | Timeout de acesso ao Redis. |
| `CAMERA_DEFAULT_MANUFACTURER` | `dahua` | Fabricante default usado quando o cadastro no Redis não informa fabricante. |
| `CAMERA_DEFAULT_PORT` | `554` | Porta RTSP default usada ao montar a URL da câmera. |
| `CAMERA_DEFAULT_CHANNEL` | `1` | Canal default usado para montar RTSP em fabricantes suportados. |
| `CAMERA_DEFAULT_SUBTYPE` | `0` | Subtipo default usado para montar RTSP em fabricantes suportados. |

### WebRTC / WHEP

| Variável | Padrão | Uso |
| --- | --- | --- |
| `WEBRTC_PORT` | `8889` | Porta HTTP/WebRTC/WHEP do MediaMTX. |
| `WHEP_URL` | `http://localhost:8889` | Base pública usada pelo endpoint bearer `/api/stream/{camera}` para montar a URL WHEP devolvida ao cliente. |
| `WEBRTC_USER` | `viewer` | Usuário de autenticação básica do WebRTC quando o projeto não está usando Keycloak e não está em `internal_jwt`. |
| `WEBRTC_PASS` | `strongpassword` | Senha correspondente ao usuário WebRTC. |
| `PUBLIC_WEBRTC_HOST` | `localhost` | Host anunciado ao MediaMTX para negociação WebRTC. Em ambiente externo, use IP ou DNS público. |
| `WEBRTC_STUN_SERVER` | `stun:stun.l.google.com:19302` | Servidor STUN padrão entregue ao frontend. |

### Keycloak

| Variável | Padrão | Uso |
| --- | --- | --- |
| `KEYCLOAK_REALM` | `mediamtx` | Realm usado para login e validação de token. |
| `KEYCLOAK_BASE_URL` | `http://localhost:8080` | URL base do Keycloak externo. |
| `KEYCLOAK_CLIENT_ID` | `mediamtx` | Client ID usado no fluxo de login. |
| `KEYCLOAK_CLIENT_SECRET` | `mediamtx-dev-secret` | Client secret do client acima. |
| `KEYCLOAK_CERTIFICATE` | vazio | Certificado PEM público opcional usado como fallback de validação de token quando o JWKS externo falha. |
| `KEYCLOAK_JWKS_CACHE_TTL_SECONDS` | `300` | Cache do JWKS externo em segundos. |
| `STREAM_ACCESS_ROLE` | `stream:read` | Papel exigido para acessar câmeras. |

### JWT interno para o MediaMTX

| Variável | Padrão | Uso |
| --- | --- | --- |
| `MEDIAMTX_JWT_ISSUER` | `stream-api` | `iss` dos JWTs emitidos pela API para o MediaMTX. |
| `MEDIAMTX_JWT_PRIVATE_KEY` | vazio | Chave privada PEM inline usada para assinar JWT. Tem precedência sobre `MEDIAMTX_JWT_PRIVATE_KEY_PATH`. |
| `MEDIAMTX_JWT_PRIVATE_KEY_PATH` | vazio | Caminho para arquivo PEM da chave privada. Só é usado quando `MEDIAMTX_JWT_PRIVATE_KEY` está vazio. |
| `MEDIAMTX_JWT_KID` | `mediamtx-internal-dev` | `kid` usado no JWT/JWKS. |
| `MEDIAMTX_JWT_TTL_SECONDS` | `60` | TTL do token de viewer. |
| `MEDIAMTX_API_TOKEN_TTL_SECONDS` | `60` | TTL do token de API usado para falar com o MediaMTX. |
| `MEDIAMTX_ADMIN_SUBJECT` | `mediamtx-admin` | `sub` do token de API emitido para o MediaMTX. |

Observação importante:

- Se `MEDIAMTX_JWT_PRIVATE_KEY` e `MEDIAMTX_JWT_PRIVATE_KEY_PATH` estiverem vazias, a API gera uma chave RSA em memória a cada boot. Isso é aceitável para desenvolvimento, mas não é ideal para produção ou múltiplas réplicas.

### TURN / ICE

| Variável | Padrão | Uso |
| --- | --- | --- |
| `TURN_ENABLED` | `false` | Habilita a entrega de servidores TURN no payload da API. |
| `TURN_PUBLIC_IP` | vazio | IP público ou IP LAN do host TURN. No macOS, use o IP da máquina na rede local. |
| `TURN_PORT` | `3478` | Porta do servidor TURN. |
| `TURN_USERNAME` | `turnuser` | Usuário do TURN. |
| `TURN_PASSWORD` | `turnpassword` | Senha do TURN. |

### Regras de negócio

| Variável | Padrão | Uso |
| --- | --- | --- |
| `MAX_VIEWERS` | `20` | Quantidade máxima de viewers simultâneos por câmera. |
| `MEDIAMTX_READY_TIMEOUT_SECONDS` | `20` | Tempo máximo para o MediaMTX marcar o stream como pronto. |
| `IDLE_ROOM_CLEANUP_SECONDS` | `20` | Intervalo de limpeza de paths ociosos. Se `0`, desativa a thread de limpeza. |

### Variável opcional para execução local

| Variável | Padrão | Uso |
| --- | --- | --- |
| `FRONT_DIR` | vazio | Diretório alternativo dos arquivos estáticos do frontend quando a API não deve servir `./front` ou `/app/front`. |

### Variáveis injetadas pelo Compose

Essas variáveis são usadas pela aplicação, mas no modo Docker elas são definidas diretamente pelo `docker-compose.yaml`, não pelo `.env.example`:

| Variável | Valor no Compose | Uso |
| --- | --- | --- |
| `MEDIAMTX_HOST` | `mediamtx` | Host interno usado pelo container da API para falar com o MediaMTX. |
| `MEDIAMTX_API` | `http://mediamtx:9997` | URL interna da API do MediaMTX no Docker network. |

## Como rodar com Docker

### 1. Preparar o `.env`

```bash
cp .env.example .env
```

Edite o arquivo e preencha principalmente:

- `KEYCLOAK_BASE_URL`
- `KEYCLOAK_REALM`
- `KEYCLOAK_CLIENT_ID`
- `KEYCLOAK_CLIENT_SECRET`
- `STREAM_ACCESS_ROLE`

Se quiser usar TURN também ajuste:

- `TURN_ENABLED=true`
- `TURN_PUBLIC_IP`
- `TURN_PORT`
- `TURN_USERNAME`
- `TURN_PASSWORD`

### 2. Subir a stack principal

```bash
docker compose up -d --build
```

### 3. Acessar a aplicação

- Login: `http://localhost:8000/`
- Player: `http://localhost:8000/player`
- Swagger/OpenAPI: `http://localhost:8000/docs`

### 4. Ver logs

```bash
docker compose logs -f api mediamtx redis
```

### 5. Parar a stack

```bash
docker compose down
```

## Como rodar com TURN

Use o overlay de TURN quando precisar melhorar conectividade WebRTC em redes NAT mais restritivas.

```bash
docker compose -f docker-compose.yaml -f docker-compose.turn.yaml up -d --build
```

Observações:

- Em macOS, `TURN_PUBLIC_IP` deve ser o IP LAN da máquina.
- Em Linux, para testes locais simples você pode manter o stack sem TURN e só habilitar esse overlay quando realmente precisar.
- O overlay publica a porta TURN configurada e o range UDP `49160-49200`.

## Como rodar a API localmente

### Serviços auxiliares

Suba apenas o Redis pela stack principal:

```bash
docker compose up -d redis
```

Observação importante:

- O `mediamtx` do `docker-compose.yaml` foi configurado para buscar o JWKS em `http://api:8000/.well-known/jwks.json`, ou seja, ele espera que a API esteja em container.
- Se a API estiver rodando no host, o MediaMTX precisa apontar para o host e não para o serviço `api` do Compose.

### Linux

Suba um MediaMTX isolado apontando o JWKS para a máquina host:

```bash
docker run --rm --name mediamtx-local \
  --add-host=host.docker.internal:host-gateway \
  -e MTX_WEBRTCADDITIONALHOSTS=localhost \
  -e MTX_AUTHJWTJWKS=http://host.docker.internal:8000/.well-known/jwks.json \
  -v "$PWD/mediamtx/mediamtx.yml:/mediamtx.yml:ro" \
  -p 8554:8554 \
  -p 8888:8888 \
  -p 8889:8889 \
  -p 8189:8189/udp \
  -p 8189:8189/tcp \
  -p 9997:9997 \
  bluenviron/mediamtx:1.15.4
```

Em outro terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

set -a
source .env
set +a

export MEDIAMTX_HOST=http://localhost
export MEDIAMTX_API=http://localhost:9997
export CAMERA_REDIS_URL=redis://localhost:6379/0

uvicorn app.main:app --app-dir api --reload --host 0.0.0.0 --port 8000
```

### macOS

Se estiver usando Docker Desktop, garanta que ele esteja iniciado. Se estiver usando Colima, rode `colima start` antes.

Suba um MediaMTX isolado apontando o JWKS para `host.docker.internal`:

```zsh
docker run --rm --name mediamtx-local \
  -e MTX_WEBRTCADDITIONALHOSTS=localhost \
  -e MTX_AUTHJWTJWKS=http://host.docker.internal:8000/.well-known/jwks.json \
  -v "$PWD/mediamtx/mediamtx.yml:/mediamtx.yml:ro" \
  -p 8554:8554 \
  -p 8888:8888 \
  -p 8889:8889 \
  -p 8189:8189/udp \
  -p 8189:8189/tcp \
  -p 9997:9997 \
  bluenviron/mediamtx:1.15.4
```

Em outro terminal:

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

set -a
source .env
set +a

export MEDIAMTX_HOST=http://localhost
export MEDIAMTX_API=http://localhost:9997
export CAMERA_REDIS_URL=redis://localhost:6379/0

uvicorn app.main:app --app-dir api --reload --host 0.0.0.0 --port 8000
```

Observação importante:

- A aplicação não faz `load_dotenv()` automaticamente. Ao rodar fora do Docker, você precisa exportar as variáveis do `.env` no shell antes de iniciar o `uvicorn`.
- Nesse modo local, o container `mediamtx-local` substitui o serviço `mediamtx` do Compose.

## Catálogo de câmeras

As câmeras podem vir de duas fontes:

- Redis, usando o prefixo `CAMERA_REDIS_PREFIX`
- fallback estático em `api/app/domain/cameras.py`

O cadastro Redis pode estar em:

- string JSON
- hash Redis

Campos aceitos pelo catálogo incluem:

- `manufacturer` / `fabricante` / `brand` / `vendor`
- `ip` / `host` / `ip_address`
- `username` / `usuario` / `user`
- `password` / `senha` / `pass`
- `port`
- `channel`
- `subtype`
- `rtsp_path`
- `rtsp_url`

## Portas expostas

| Porta | Serviço | Descrição |
| --- | --- | --- |
| `8000` | API | FastAPI, frontend e JWKS |
| `8554` | MediaMTX | RTSP |
| `8888` | MediaMTX | HLS fallback |
| `8889` | MediaMTX | WebRTC/WHEP HTTP |
| `8189/tcp` | MediaMTX | ICE TCP |
| `8189/udp` | MediaMTX | ICE UDP |
| `9997` | MediaMTX | API administrativa |

## Observações operacionais

- O projeto atual espera um Keycloak externo; o serviço local de Keycloak no `docker-compose.yaml` está comentado.
- O endpoint `/api/stream/{camera}` é o fluxo bearer para integrações que não usam a tela de login, integração via API.
- Se você configurar `MEDIAMTX_JWT_PRIVATE_KEY`, ela precisa ser uma chave privada PEM válida. Se ela vier inválida, a API falha ao gerar o token para o MediaMTX.
- No modo Docker, o `MediaMTX` busca o JWKS da API para validar os JWTs internos emitidos pelo backend.

## Possíveis erros

Esta seção resume os erros mais comuns do projeto e o que normalmente precisa ser verificado.

### Erros comuns da API

| Sintoma | Causa provável | O que verificar |
| --- | --- | --- |
| `401 bearer_token_missing` | O endpoint `/api/stream/{camera}` foi chamado sem header `Authorization: Bearer ...` | Verifique o cliente chamador e o token enviado. |
| `401 external_token_invalid` | Token JWT externo inválido, expirado, com `issuer` errado ou assinado por chave não reconhecida | Revise `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CERTIFICATE` e o token recebido. |
| `401 session_missing_or_expired` | Cookie de sessão HTTP expirou ou não foi enviado | Faça login novamente na UI em `/` e confira se o browser está enviando cookies. |
| `403 camera_access_denied` | O usuário autenticado não possui o papel exigido para a câmera | Confirme `STREAM_ACCESS_ROLE` e os papéis presentes no token do Keycloak. |
| `404 camera_not_found` | A câmera não existe no Redis nem no fallback estático | Verifique o cadastro da câmera no Redis e o `device_name` solicitado. |
| `429 viewers_limit_reached` | A quantidade de viewers da câmera atingiu `MAX_VIEWERS` | Ajuste `MAX_VIEWERS` ou encerre viewers abertos. |
| `500 turn_public_ip_missing` | `TURN_ENABLED=true`, mas `TURN_PUBLIC_IP` não foi configurado | Defina `TURN_PUBLIC_IP`. |
| `500 turn_credentials_missing` | `TURN_ENABLED=true`, mas `TURN_USERNAME` ou `TURN_PASSWORD` está vazio | Defina as credenciais do TURN. |
| `503 session_store_unavailable` | Redis indisponível ou inacessível pela API | Verifique o container `redis`, `CAMERA_REDIS_URL` e conectividade entre API e Redis. |
| `503 mediamtx_unavailable` | A API não conseguiu falar com o MediaMTX | Veja a subseção específica abaixo. |

### `503 mediamtx_unavailable`

Esse erro é genérico e precisa ser lido junto com o traceback do log da API.

Causas frequentes:

- `MEDIAMTX_API` incorreto
- `MEDIAMTX_HOST` incorreto
- MediaMTX não subiu
- porta errada
- falha de autenticação JWT entre API e MediaMTX
- URL WHEP upstream malformada

Exemplos reais já vistos neste projeto:

- `No connection adapters were found for 'mediamtx:8889/camera02/whep'`
  - significa que a URL foi montada sem `http://`
- erro ao chamar `/v3/paths/list`
  - indica problema na autenticação da API do MediaMTX ou indisponibilidade da API administrativa

O que verificar:

- `docker compose ps`
- `docker compose logs -f mediamtx`
- valor de `MEDIAMTX_API` dentro da API
- valor de `MEDIAMTX_HOST` dentro da API
- se `http://localhost:9997/v3/paths/list` responde no host

### Erros de chave JWT do MediaMTX

Sintoma comum:

```text
ValueError: Could not deserialize key data
```

Significado:

- `MEDIAMTX_JWT_PRIVATE_KEY` ou `MEDIAMTX_JWT_PRIVATE_KEY_PATH` aponta para uma chave inválida

O que costuma causar isso:

- conteúdo PEM malformado
- arquivo errado
- certificado público em vez de chave privada
- chave criptografada com senha
- variável inline com quebras de linha quebradas

Formato esperado:

```pem
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

Observações:

- `MEDIAMTX_JWT_PRIVATE_KEY` tem precedência sobre `MEDIAMTX_JWT_PRIVATE_KEY_PATH`
- se ambas estiverem vazias, a API gera uma chave em memória no boot

### Erros de Keycloak

| Sintoma | Causa provável | O que verificar |
| --- | --- | --- |
| `401 Falha ao autenticar no Keycloak` | usuário/senha inválidos, client incorreto ou client secret incorreto | Valide credenciais do usuário e os campos `KEYCLOAK_CLIENT_ID` e `KEYCLOAK_CLIENT_SECRET`. |
| `503 Keycloak indisponivel no momento` | a API não conseguiu obter token do Keycloak | Verifique `KEYCLOAK_BASE_URL`, conectividade e disponibilidade do realm. |
| falhas de JWKS externo | API não conseguiu baixar as chaves públicas do Keycloak | Verifique `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM` e se o endpoint `/protocol/openid-connect/certs` responde. |

### Erros de câmera / RTSP

| Sintoma | Causa provável | O que verificar |
| --- | --- | --- |
| `camera_offline` | câmera desligada, inacessível na rede ou timeout RTSP | Teste conectividade com a câmera e valide IP/porta. |
| `camera_auth_failed` | credenciais RTSP erradas | Revise usuário e senha da câmera no Redis ou no fallback local. |
| `camera_url_invalid` | URL RTSP inválida ou path RTSP incorreto | Revise `rtsp_url`, `rtsp_path`, `manufacturer`, `channel`, `subtype` e `port`. |
| `camera_manufacturer_unsupported` | fabricante não suportado para montagem automática da URL RTSP | Use `rtsp_url` explícita ou ajuste `manufacturer`. |
| `camera_start_timeout` | a câmera respondeu, mas o MediaMTX não marcou o path como `ready` a tempo | Verifique o log do MediaMTX, o tempo em `MEDIAMTX_READY_TIMEOUT_SECONDS` e o estado real da câmera. |

### Erros de WHEP/WebRTC

| Sintoma | Causa provável | O que verificar |
| --- | --- | --- |
| o player abre, mas não toca vídeo | ICE/WebRTC não conseguiu fechar conexão | Revise `PUBLIC_WEBRTC_HOST`, `WEBRTC_STUN_SERVER` e, se necessário, habilite TURN. |
| falha apenas fora da rede local | host anunciado pelo MediaMTX está errado | Ajuste `PUBLIC_WEBRTC_HOST` para IP ou DNS acessível externamente. |
| falha em redes restritas ou NAT | falta de TURN | Use `docker-compose.turn.yaml`, configure `TURN_ENABLED=true` e preencha as variáveis TURN. |

### Erros específicos de execução local

| Sintoma | Causa provável | O que verificar |
| --- | --- | --- |
| `ffprobe` não encontrado | `ffmpeg` não está instalado no host | Instale `ffmpeg` e confirme `ffprobe` no `PATH`. |
| MediaMTX sobe, mas não valida JWT da API local | o JWKS do MediaMTX aponta para `api:8000` em vez do host | No modo local, use o comando do README com `MTX_AUTHJWTJWKS=http://host.docker.internal:8000/.well-known/jwks.json`. |
| API local não encontra variáveis do `.env` | as variáveis não foram exportadas no shell | Rode `set -a; source .env; set +a` antes do `uvicorn`. |
