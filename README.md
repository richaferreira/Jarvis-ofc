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
