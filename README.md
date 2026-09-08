# J.A.R.V.I.S. — Jarvis-ofc

Assistente pessoal em Python com LangGraph, modelos OpenAI/Gemini/Ollama, Whisper local, voz Edge-TTS/ElevenLabs, memória ChromaDB e integração com Home Assistant.

O projeto inclui os seis passos: configuração e ferramentas, áudio, RAG, agente e execução assíncrona. Pode ser usado pelo terminal, microfone ou API. O modo padrão é local com Ollama; serviços externos precisam da sua configuração. Não há chaves, senhas ou dados pessoais neste repositório.

## Início rápido no Windows (PowerShell)

Use Python **3.11 de 64 bits** como referência. O núcleo também tem CI em Python 3.12. A instalação completa baixa pacotes de ML e pode ocupar vários GB.

```powershell
git clone https://github.com/richaferreira/Jarvis-ofc.git
cd Jarvis-ofc
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3.0" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Instale [Ollama](https://ollama.com/download). Com o serviço em execução, baixe o modelo configurado:

```powershell
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m app.main --mode text
```

O modelo é uma sugestão inicial configurável, não uma exigência. Escolha um modelo com **tool calling** e tamanho compatível com sua RAM/VRAM. Na primeira execução com memória, o modelo de embeddings também é baixado. O modo texto não carrega Whisper nem acessa o microfone.

Para falar, instale [FFmpeg](https://ffmpeg.org/download.html) incluindo **ffplay**, coloque seus executáveis no PATH e abra outro PowerShell. Verifique:

```powershell
ffmpeg -version
ffplay -version
.\.venv\Scripts\python.exe -m app.main --list-devices
.\.venv\Scripts\python.exe -m app.main --mode voice
```

Se necessário, ajuste `AUDIO_DEVICE` com o índice do microfone e permita o acesso a aplicativos de desktop nas configurações de privacidade do Windows. A captura usa mono a 16 kHz. `SPEECH_THRESHOLD` controla a sensibilidade: reduza se não detectar sua fala; aumente se ruído iniciar gravações. `SILENCE_SECONDS` determina o fim da frase. Não há wake word nem escuta durante a reprodução do próprio áudio; use Ctrl+C para encerrar.

## Linux

```bash
sudo apt-get update
sudo apt-get install -y python3-venv ffmpeg libportaudio2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'torch>=2.6,<3.0' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.main --mode text
```

Use um Python 3.11 ou 3.12 disponível no sistema. Em macOS, use a instalação de PyTorch apropriada ao sistema, não o índice Linux/Windows CPU. CUDA exige a distribuição de PyTorch compatível com seu driver; só então configure `WHISPER_DEVICE=cuda`.

## Escolher o LLM

Edite `.env`, sem alterar código:

| Provedor | Configuração |
|---|---|
| Ollama | `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen3:8b`, `OLLAMA_BASE_URL=http://127.0.0.1:11434` |
| OpenAI | `LLM_PROVIDER=openai`, `LLM_MODEL=<modelo habilitado na sua conta com tools>`, `OPENAI_API_KEY=<sua chave>` |
| Gemini | `LLM_PROVIDER=gemini`, `LLM_MODEL=<modelo habilitado na sua conta com tools>`, `GOOGLE_API_KEY=<sua chave>` |

A Factory importa somente o provedor selecionado. Modelos locais pequenos podem não chamar ferramentas corretamente; isso depende do modelo, não apenas da biblioteca. Não existe troca automática de provedor: ela poderia enviar dados a outro serviço sem uma escolha explícita.

## Comandos de texto e memória

```text
Que horas são?
Pesquise novidades sobre Python e mostre os links.
Como está o clima em Saquarema?
/remember Prefiro respostas em português brasileiro.
/clear
/forget
/exit
```

`/remember` grava uma preferência por solicitação explícita, com até 2.000 caracteres. `/forget` pede confirmação e apaga suas preferências das coleções do aplicativo, inclusive de modelos de embeddings anteriores. `/clear` limpa a conversa atual e revoga suas ações pendentes. As preferências são isoladas pelo proprietário; o histórico recente é limitado em quantidade, caracteres, sessões e tempo.

A busca RAG é semântica: não garante recuperar toda preferência relevante. Preferências conflitantes devem ser apagadas e regravadas. Conteúdo recuperado nunca autoriza ações automaticamente. O aplicativo não armazena toda conversa no banco vetorial. Dados em `data/` são locais e **não são criptografados pelo aplicativo**; proteja o dispositivo e faça backups conforme sua necessidade. A troca do embedding cria outra coleção, evitando mistura de dimensões.

Para testar somente o núcleo sem baixar pesos:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
```

Configure `MEMORY_ENABLED=false` e use `--mode text` ou `--mode api`. Ainda é necessário um LLM acessível. Essa opção desativa explicitamente a memória de longo prazo.

## Voz

Whisper `base` favorece consumo menor; `small` costuma exigir mais processamento. STT executa localmente após o download dos pesos. Edge-TTS e ElevenLabs são **online**. Para ElevenLabs, configure `TTS_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID`; a integração usa REST via HTTPX, sem necessidade de instalar outro SDK.

O cache em disco considera texto, provedor, voz, modelo e formato. Ele tem expiração e limite de espaço. Respostas longas permanecem completas na tela; a parte falada é limitada por `TTS_MAX_CHARS`. Se o TTS falhar, o texto continua disponível. Não há promessa de latência subsegundo: CPU/GPU, tamanho do modelo, duração da fala e rede influenciam o tempo. Os pesos são carregados uma vez, e operações bloqueantes saem do event loop.

## Home Assistant

No Home Assistant, crie um token de acesso de longa duração para a integração e identifique as entidades reais. Configure, por exemplo:

```dotenv
HOME_ASSISTANT_URL=http://192.168.1.10:8123
HOME_ASSISTANT_TOKEN=<seu_token>
HOME_ACTIONS={"ligar_sala":{"description":"Ligar a luz da sala","domain":"light","service":"turn_on","entity_ids":["light.sala"]}}
```

Substitua IP, token e entidade. `HOME_ACTIONS` precisa ser JSON válido em uma linha. Para webhook, use uma ação com `description` e `webhook_id`, sem os campos de serviço. O webhook precisa existir na sua automação, aceitar POST e permitir a origem local do J.A.R.V.I.S. Seu identificador é um segredo.

Peça “Ligue a luz da sala”. O agente lista/propõe uma ação; a interface mostra o alvo e um token. No modo texto, execute **`/confirm TOKEN`**. No modo voz, a confirmação é digitada após a leitura, para impedir que áudio ambiente autorize o comando. O LLM não recebe uma ferramenta capaz de confirmar.

Cada token expira, pertence a uma sessão e pode ser utilizado uma vez. O POST não tem retry automático: se a conexão cair, verifique o dispositivo antes de criar outra ação. Uma resposta HTTP de sucesso indica solicitação aceita pelo Home Assistant, não comprova o estado físico do equipamento. As ações executam somente serviços/entidades ou webhooks pré-configurados, sem URLs ou payloads arbitrários sugeridos pelo modelo.

## API autenticada

Gere um token e coloque-o em `API_TOKEN` no `.env`:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe -m app.main --mode api
```

A API escuta em `127.0.0.1:8000` por padrão e usa **um worker**. Exemplo PowerShell, com o token correspondente:

```powershell
$jarvisToken = Read-Host "API_TOKEN"
$jarvisHeaders = @{Authorization = "Bearer $jarvisToken"}
$jarvisBody = @{session_id = "desktop"; message = "Que horas são?"} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -Headers $jarvisHeaders -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($jarvisBody))
```

| Endpoint | Uso |
|---|---|
| `GET /health` | Prontidão após inicialização; público, não testa a disponibilidade do LLM. |
| `POST /chat` | Corpo `{"session_id":"desktop","message":"Olá"}`. |
| `POST /actions/confirm` | Corpo `{"session_id":"desktop","token":"TOKEN_RECEBIDO"}`. |
| `POST /memory` | Corpo `{"text":"Prefiro português"}`. |
| `DELETE /memory` | Apaga preferências do proprietário; chamada autenticada já constitui autorização. |
| `DELETE /sessions/desktop` | Limpa histórico dessa sessão e propostas pendentes. |

Todos, exceto `/health`, exigem Bearer token. A API representa **um proprietário**; `session_id` separa conversas, não é um sistema multiusuário. O token dá acesso a confirmações e memória: não o distribua a terceiros. Não há upload HTTP de áudio nesta versão; o áudio é capturado no terminal local. Para publicar na rede, configure TLS, autenticação por usuário e limites de tráfego em um gateway; não exponha o servidor de desenvolvimento diretamente.

## Testes e dependências reproduzíveis

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes exercitam o grafo LangGraph real com modelo falso determinístico, confirmações concorrentes e expiradas, falhas HTTP, separação de sessões, cache, autenticação, limites de corpo e persistência Chroma entre processos. As chamadas IoT e provedores pagos são simuladas; não é necessário fornecer segredos ao CI.

[GitHub Actions](https://github.com/richaferreira/Jarvis-ofc/actions) instala/testa o núcleo em Python 3.11/3.12 e verifica a instalação completa CPU em Python 3.11. Cada execução bem-sucedida publica a lista de versões resolvidas em um artefato. As faixas `requirements*.txt` **não são lockfiles**: use o artefato correspondente ao seu sistema como base para congelar uma implantação, revisando índice de PyTorch e hashes. A validação no Windows, microfone real, qualidade das vozes, GPU e comandos físicos continua sendo parte da homologação no dispositivo de destino.

## Organização

| Diretório/arquivo | Responsabilidade |
|---|---|
| `app/config.py` | Configuração `.env`, tipagem e validação. |
| `app/core/` | Factory, contratos, mensagens e grafo cognitivo. |
| `app/tools/` | Busca DuckDuckGo, clima Open-Meteo, hora e Home Assistant. |
| `app/audio/` | Microfone, Whisper, TTS e reprodução. |
| `app/memory/` | Singleton Chroma, embeddings, RAG e histórico. |
| `app/infrastructure/` | HTTP, cache e workers bloqueantes limitados. |
| `app/runtime.py` | Inicialização e encerramento dos serviços. |
| `app/api/server.py` | API autenticada. |
| `app/main.py` | Loop assíncrono e entrada CLI. |
| `tests/` | Testes de unidade e integração. |
| `docs/architecture.md` | Decisões, fluxos e limites de escala. |

## Fontes das integrações

- [LangGraph](https://docs.langchain.com/oss/python/langgraph/quickstart)
- [Integrações LangChain](https://docs.langchain.com/oss/python/integrations/providers/overview)
- [Whisper](https://github.com/openai/whisper)
- [Edge-TTS](https://github.com/rany2/edge-tts)
- [ElevenLabs REST](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
- [Chroma e concorrência](https://cookbook.chromadb.dev/core/system_constraints/)
- [DDGS](https://pypi.org/project/ddgs/) — cliente de terceiros, sujeito a bloqueios e limites; não é uma API oficial DuckDuckGo com SLA.
- [Open-Meteo](https://open-meteo.com/en/docs) — observe atribuição, limites e condições aplicáveis ao seu uso, especialmente comercial.
- [Home Assistant REST](https://developers.home-assistant.io/docs/api/rest/)

## Inicialização do núcleo híbrido

Na branch `architecture/hybrid-realtime`, o checkout completo oferece um novo modo:

```bash
python -m pip install uv==0.10.0
python -m app.main --mode hybrid --hybrid-host 127.0.0.1 --hybrid-port 8000
```

Prepare antes `examples/hybrid/.env` e os serviços conforme o
[guia híbrido](examples/hybrid/README.md). O comando usa o `uv.lock` desse
subprojeto e lê seu `.env`; não precisa instalar Whisper ou as dependências
da aplicação desktop. Para executar o agente fora do Docker, configure nesse
`.env` os endereços alcançáveis do ChromaDB, Neo4j, MQTT e Ollama. Os nomes
`chroma`, `neo4j` e `mqtt` da rede Compose não são resolvidos pelo host.
O Compose completo continua sendo a opção pronta para a rede interna.

O processo mantém o código de saída do serviço e encerra com Ctrl+C.
O padrão escuta apenas localhost, com um worker. Este modo integra a
inicialização: o WebSocket híbrido ainda não compartilha a memória buffer,
as ferramentas de ação ou o pipeline de voz da aplicação desktop.
A instalação por wheel sem `examples/hybrid` não oferece esse modo.

## Central de comando Windows

Abra `JARVIS.bat` na raiz do checkout completo. O painel ciano sobre fundo
preto oferece instalacao automatizada da `.venv`, configuracao, modos voz,
texto e API, dispositivos de audio, gerenciamento do Compose hibrido e
diagnostico sem exibir segredos. A instalacao cria `.env` apenas quando
ausente; preencha o provedor e as credenciais antes de iniciar o assistente.

Use Python 3.11 ou 3.12. Voz requer FFmpeg/ffplay no PATH e microfone.
O hibrido requer Docker Desktop com conteineres Linux, configuracao de
segredos e usuarios do broker conforme `examples/hybrid/README.md`.
O painel nao instala ferramentas do sistema nem baixa modelos Ollama.
A opcao P para os conteineres preservando os volumes. Fechar o painel
nao encerra servicos Docker. Ctrl+C durante o assistente pode pedir a
confirmacao padrao do Windows para encerrar o arquivo em lotes.

`JARVIS.bat --help` mostra a ajuda; `JARVIS.bat --check` executa somente
o diagnostico. Seu codigo zero indica que o diagnostico executou, nao
que todos os requisitos estao instalados. O painel tambem funciona quando
iniciado de outra pasta, pois usa a localizacao do proprio arquivo.

## Interface visual em português

A opção 5 do `JARVIS.bat` inicia a API com o painel visual. Configure
`API_TOKEN` no `.env` (pelo menos 32 caracteres aleatórios), abra
`http://127.0.0.1:8000` e conecte-se com esse token. Se alterar API_HOST ou
API_PORT, use o endereço correspondente. O token permanece apenas na memória
da página; recarregar exige reconectar. O painel não edita arquivos de segredos.

A interface oferece conversa real, preferências persistentes, limpeza de sessão,
confirmação de ações domésticas e diagnóstico do inventário Ollama. Modelo
instalado não significa inferência validada. Os indicadores nunca simulam
CPU, agentes ou conexões inexistentes. O endpoint legado /chat retorna respostas completas;
streaming GraphRAG continua no serviço híbrido separado.

Ditado e leitura em voz alta usam recursos opcionais do navegador, não o
Whisper/Edge-TTS do desktop. O ditado pode usar processamento online e pede
consentimento antes de ativar. A interface é responsiva e respeita a preferência
de movimento reduzido. Não é uma implementação de áudio full-duplex.

Se houver ResponseError, teste `ollama list` e `ollama run qwen3:8b`. O painel
consulta `/api/tags` pelo servidor e diferencia modelo ausente de serviço
inacessível; chamadas ao modelo apresentam mensagens próprias para 400, 404,
5xx e timeout, sem revelar prompts ou credenciais do provedor. O aviso de
HF_TOKEN no primeiro download de embeddings não implica falha do Ollama.

## OmniRoute: múltiplos provedores pelo mesmo gateway

Integração com https://github.com/diegosouzapw/OmniRoute pelo protocolo
OpenAI Chat Completions. Instale o gateway seguindo as instruções oficiais
(`npm install -g omniroute`, com Node compatível), execute `omniroute` em
outro terminal e abra http://127.0.0.1:20128. Conecte seus provedores e
configure um modelo ou combo com suporte a ferramentas. Gere uma chave em
Endpoints no painel do gateway. Os custos, cotas, permissões e disponibilidade
continuam sendo os de cada provedor.

No `.env` da raiz, edite as linhas existentes (não duplique):

```dotenv
LLM_PROVIDER=omniroute
LLM_MODEL=ID_EXATO_DO_MODELO_OU_COMBO
OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1
OMNIROUTE_API_KEY=CHAVE_GERADA_NO_GATEWAY
API_TOKEN=TOKEN_PROPRIO_DO_JARVIS_COM_PELO_MENOS_32_CARACTERES
```

`API_TOKEN` autentica o navegador no Jarvis. `OMNIROUTE_API_KEY` autentica
o Jarvis no gateway; nunca é enviada ao navegador. As chaves dos provedores
ficam cadastradas no OmniRoute. O painel Jarvis exibe o catálogo autenticado
e permite filtrá-lo; copie o ID desejado para `LLM_MODEL` e reinicie.
Criar conexões, editar combos e gerenciar credenciais ocorre no painel
OmniRoute. Não há troca de configuração global durante uma conversa.

O agente usa as mesmas ferramentas e confirmação de ações. O gateway
controla os fallbacks configurados; o cliente Jarvis não adiciona retries.
A consulta de catálogo não prova que uma inferência funciona. Teste uma
conversa depois de conectar os provedores.

Para o serviço híbrido, configure o `.env` em `examples/hybrid`, usando
`http://host.docker.internal:20128/v1` quando o gateway roda no host e é
alcançável pelo contêiner. Os embeddings híbridos ainda usam Ollama; mudar
o provedor de chat não muda o modelo vetorial.

Se o navegador mostrar conexão recusada, o servidor não está acessível no
endereço informado. Inicie a opção 5 e aguarde a mensagem do Uvicorn.
API_TOKEN ausente ou curto agora produz uma explicação direta no terminal.
Não feche a janela do servidor enquanto usa o painel.

## Melhorias para teste: conversa, voz e inicialização

O painel agora usa `/chat/stream` autenticado, com tokens progressivos reais
do modelo. A seleção de modelo vale para o pedido, sem alterar o `.env`
em execução ou compartilhar configuração mutável entre sessões. Apenas
IDs do catálogo autenticado podem substituir o modelo padrão. Combos e
credenciais continuam no gateway. Rodadas intermediárias de ferramentas
podem substituir o texto provisório; a mensagem final é a confirmada.

As conversas concluídas são persistidas em `data/conversations.sqlite3`
(até 64 sessões por proprietário, 30 pares por sessão). O histórico permite
reabrir conversas após reiniciar o servidor. Limpar conversa remove seus
registros e revoga ações pendentes; preferências RAG permanecem separadas.
O histórico é local e não criptografado. Tokens de ações e credenciais não
são gravados no histórico. Cancelamento não desfaz uma ação já confirmada.

O seletor fica sobre a conversa, acompanhado de Nova conversa e Interromper.
Modo foco amplia a área de diálogo. A interface foi ajustada para celular.
Voz contínua é opcional: após consentimento, o reconhecimento do navegador
envia a transcrição e a detecção de início de fala interrompe a síntese e
a requisição ativa. Use fones para evitar reconhecimento do próprio áudio.
A disponibilidade e qualidade dependem do navegador; isso não substitui o
Whisper desktop nem fornece VAD neural local. Interromper também desativa
a escuta contínua. O fechamento do stream cancela a tarefa no servidor.

A opção 5 reserva uma porta livre entre API_PORT e API_PORT+9 antes de
carregar os modelos, imprime o endereço real e abre o navegador após
`/health` responder. Um API_TOKEN ausente/curto é gerado e salvo no `.env`.
Se OmniRoute estiver configurado em localhost mas não estiver escutando,
o launcher tenta iniciar o comando `omniroute` já instalado no PATH.
Não instala o gateway nem altera suas credenciais; confira sua janela.
A configuração de API_TOKEN válida é preservada.

Roteiro: iniciar opção 5; conectar; selecionar modelo; enviar mensagem e
observar tokens; interromper; abrir nova conversa; reabrir histórico;
reiniciar e reabrir histórico; testar voz com fones e consentimento; ocupar
a porta padrão com outro serviço e confirmar o endereço alternativo.
