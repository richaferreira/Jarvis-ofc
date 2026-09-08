@echo off
setlocal EnableExtensions DisableDelayedExpansion
title J.A.R.V.I.S. - CENTRAL DE COMANDO
color 0B
pushd "%~dp0" || exit /b 1
set "JARVIS_RESULT=0"
set "JARVIS_PY="
if /i "%~1"=="--help" goto help
if /i "%~1"=="--check" goto check
if not "%~1"=="" goto invalid
if not exist "app\main.py" goto missing
:menu
cls
call :banner
echo     SISTEMA MODULAR  /  INTELIGENCIA  /  AUTOMACAO RESIDENCIAL
echo.
echo     [1] INSTALAR AMBIENTE        Nucleo + voz + memoria local
echo     [2] CONFIGURAR DESKTOP      Criar ou editar .env
echo     [3] INICIAR VOZ             Microfone + Whisper + TTS
echo     [4] INICIAR TEXTO           Console de conversacao
echo     [5] INTERFACE WEB           Painel visual em PT-BR
echo     [6] DISPOSITIVOS DE AUDIO   Listar entradas e saidas
echo.
echo     [7] CONFIGURAR HIBRIDO      Editar .env e abrir guia MQTT
echo     [8] INICIAR DOCKER          Agente + Chroma + Neo4j + MQTT
echo     [9] STATUS DOCKER           Estado dos servicos
echo     [P] PARAR DOCKER            Preservar bancos e volumes
echo.
echo     [D] DIAGNOSTICO             Python, audio, Docker e arquivos
echo     [G] GUIA DO PROJETO         Documentacao completa
echo     [0] ENCERRAR CENTRAL
echo.
choice /c 123456789PDG0 /n /m "    COMANDO: "
if errorlevel 255 goto finish
if errorlevel 13 goto finish
if errorlevel 12 goto guide
if errorlevel 11 goto diagnostics
if errorlevel 10 goto docker_stop
if errorlevel 9 goto docker_status
if errorlevel 8 goto docker_start
if errorlevel 7 goto hybrid_config
if errorlevel 6 goto devices
if errorlevel 5 goto api
if errorlevel 4 goto text
if errorlevel 3 goto voice
if errorlevel 2 goto config
if errorlevel 1 goto install
goto finish
:banner
echo.
echo     ============================================================
echo           J . A . R . V . I . S .   /   COMMAND CENTER
echo     ============================================================
echo          [ ARC CORE ]     [ NEURAL LINK ]     [ HOME GRID ]
echo     ------------------------------------------------------------
exit /b 0
:install
cls
call :banner
echo     Instalacao local em .venv. Nao exige administrador.
echo     Os pacotes de IA podem baixar varios gigabytes.
echo     FFmpeg e modelos Ollama sao configurados separadamente.
echo.
choice /c SN /n /m "    Instalar ou reparar as dependencias? [S/N]: "
if errorlevel 2 goto menu
call :find_python
if errorlevel 1 goto operation_failed
if exist ".venv\Scripts\python.exe" goto install_packages
%JARVIS_PY% -m venv .venv
if errorlevel 1 goto operation_failed
:install_packages
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,12) else 1)"
if errorlevel 1 goto wrong_version
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto operation_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto operation_failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto operation_failed
echo.
if exist ".env" goto install_done
copy /y ".env.example" ".env" >nul
if errorlevel 1 goto operation_failed
:install_done
echo     [OK] Ambiente instalado. Configure o .env na opcao 2.
goto back
:config
if exist ".env" goto edit_config
copy /y ".env.example" ".env" >nul
if errorlevel 1 goto operation_failed
:edit_config
start "" notepad.exe "%CD%\.env"
echo     Configure provedor, modelo e credenciais no editor.
goto back
:hybrid_config
if exist "examples\hybrid\.env" goto edit_hybrid
copy /y "examples\hybrid\.env.example" "examples\hybrid\.env" >nul
if errorlevel 1 goto operation_failed
:edit_hybrid
start "" notepad.exe "%CD%\examples\hybrid\.env"
start "" notepad.exe "%CD%\examples\hybrid\README.md"
echo     Substitua os segredos de exemplo e configure o broker pelo guia.
echo     O arquivo mosquitto/passwords deve conter os usuarios jarvis e bridge.
echo     A senha de jarvis deve corresponder a MQTT_PASSWORD.
goto back
:voice
call :need_env
if errorlevel 1 goto back
where ffmpeg >nul 2>&1
if errorlevel 1 goto missing_audio
where ffplay >nul 2>&1
if errorlevel 1 goto missing_audio
".venv\Scripts\python.exe" -m app.main --mode voice
goto process_return
:text
call :need_env
if errorlevel 1 goto back
".venv\Scripts\python.exe" -m app.main --mode text
goto process_return
:api
echo     O navegador abrira quando o servidor estiver pronto.
echo     O endereco real sera exibido; portas ocupadas serao evitadas.
call :need_env
if errorlevel 1 goto back
".venv\Scripts\python.exe" -m app.main --mode api
goto process_return
:devices
call :need_python
if errorlevel 1 goto back
".venv\Scripts\python.exe" -m app.main --list-devices
goto process_return
:process_return
if errorlevel 1 goto operation_failed
echo     [OK] Processo encerrado.
goto back
:docker_start
call :need_docker
if errorlevel 1 goto back
if not exist "examples\hybrid\.env" goto missing_hybrid
if not exist "examples\hybrid\mosquitto\passwords" goto missing_hybrid
findstr /c:"SUBSTITUA_POR" "examples\hybrid\.env" >nul 2>&1
if not errorlevel 1 goto missing_hybrid
docker compose --project-directory "examples/hybrid" up -d --build --wait --wait-timeout 180
if errorlevel 1 goto operation_failed
echo     [OK] Servicos iniciados. WebSocket: ws://127.0.0.1:8000/ws
echo     Saude: http://127.0.0.1:8000/health
echo     Fechar este painel nao para os conteineres. Use P para parar.
goto back
:docker_status
call :need_docker
if errorlevel 1 goto back
if not exist "examples\hybrid\.env" goto missing_hybrid
docker compose --project-directory "examples/hybrid" ps
goto process_return
:docker_stop
call :need_docker
if errorlevel 1 goto back
if not exist "examples\hybrid\.env" goto missing_hybrid
choice /c SN /n /m "    Parar os servicos hibridos? [S/N]: "
if errorlevel 2 goto menu
rem Stop preserves containers and all persistent volumes.
docker compose --project-directory "examples/hybrid" stop
goto process_return
:diagnostics
cls
call :banner
call :report
goto back
:report
echo     [PYTHON COMPATIVEL]
call :find_python
if errorlevel 1 goto report_files
%JARVIS_PY% --version
:report_files
echo.
echo     [ARQUIVOS LOCAIS]
if exist ".venv\Scripts\python.exe" (echo     Ambiente desktop: presente) else echo     Ambiente desktop: ausente
if exist ".env" (echo     Configuracao desktop: presente) else echo     Configuracao desktop: ausente
if exist "examples\hybrid\.env" (echo     Configuracao hibrida: presente) else echo     Configuracao hibrida: ausente
if exist "examples\hybrid\mosquitto\passwords" (echo     Arquivo MQTT: presente) else echo     Arquivo MQTT: ausente
echo     Presenca de arquivo nao confirma validade de credenciais.
echo.
echo     [FERRAMENTAS NO PATH]
for %%T in (ffmpeg ffplay docker ollama) do (
    where %%T >nul 2>&1
    if errorlevel 1 (echo     %%T: ausente) else echo     %%T: encontrado
)
echo.
echo     Nenhum segredo do .env e exibido neste diagnostico.
exit /b 0
:find_python
set "JARVIS_PY="
py -3.11 -c "import sys; sys.exit(0)" >nul 2>&1
if not errorlevel 1 set "JARVIS_PY=py -3.11"
if defined JARVIS_PY exit /b 0
py -3.12 -c "import sys; sys.exit(0)" >nul 2>&1
if not errorlevel 1 set "JARVIS_PY=py -3.12"
if defined JARVIS_PY exit /b 0
python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 set "JARVIS_PY=python"
if defined JARVIS_PY exit /b 0
echo     [AVISO] Instale Python 3.11 ou 3.12 com o Python Launcher.
exit /b 1
:need_python
if exist ".venv\Scripts\python.exe" exit /b 0
echo     [AVISO] Instale o ambiente pela opcao 1.
exit /b 1
:need_env
call :need_python
if errorlevel 1 exit /b 1
if exist ".env" exit /b 0
echo     [AVISO] Configure o .env pela opcao 2.
exit /b 1
:need_docker
docker compose version >nul 2>&1
if errorlevel 1 goto docker_unavailable
docker info >nul 2>&1
if errorlevel 1 goto docker_unavailable
exit /b 0
:docker_unavailable
echo     [AVISO] Abra Docker Desktop com conteineres Linux e Compose.
exit /b 1
:missing_audio
echo     [AVISO] Instale FFmpeg com ffmpeg e ffplay disponiveis no PATH.
goto back
:missing_hybrid
echo     [AVISO] Complete a configuracao hibrida pela opcao 7.
goto back
:wrong_version
echo     [FALHA] A .venv existente deve usar Python 3.11 ou 3.12.
echo     Renomeie essa pasta antes de criar outro ambiente.
goto back
:operation_failed
echo.
echo     [FALHA] A operacao nao foi concluida. Revise a mensagem acima.
echo     Use D para diagnostico. A operacao pode ter sido parcialmente aplicada.
goto back
:guide
start "" notepad.exe "%CD%\README.md"
goto menu
:back
echo.
pause
goto menu
:check
if not exist "app\main.py" goto missing
call :banner
call :report
echo     [OK] Painel e estrutura encontrados; diagnostico concluido.
goto finish
:help
echo J.A.R.V.I.S. - Central Windows
echo Uso: JARVIS.bat [--help ou --check]
echo Sem argumentos: abre o menu interativo.
echo --check: diagnostico sem instalar ou iniciar servicos.
goto finish
:invalid
echo Argumento invalido. Use --help.
set "JARVIS_RESULT=2"
goto finish
:missing
echo [FALHA] Coloque JARVIS.bat na raiz do checkout completo Jarvis-ofc.
set "JARVIS_RESULT=2"
:finish
popd
endlocal & exit /b %JARVIS_RESULT%
