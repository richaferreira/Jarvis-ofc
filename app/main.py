"""Asynchronous CLI entry point: voice loop, text console or authenticated API."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import threading

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.runtime import Runtime


def terminal_text(text: str) -> str:
    """Remove terminal control characters from untrusted model output."""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)


async def console_input(prompt: str) -> str:
    """Read console input off the event loop; EOF requests an orderly exit."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    def deliver(value: str) -> None:
        if not future.done():
            future.set_result(value)

    def read() -> None:
        try:
            value = input(prompt)
        except (EOFError, OSError):
            value = "/exit"
        try:
            loop.call_soon_threadsafe(deliver, value)
        except RuntimeError:
            pass  # The application already shut down while the terminal was waiting.

    # Do not put interactive input into asyncio's executor: shutdown would wait for Enter.
    threading.Thread(target=read, name="console-input", daemon=True).start()
    return await future


async def handle_command(runtime: Runtime, text: str, session: str) -> bool:
    """Execute typed UI commands only; transcribed speech never enters this handler."""
    command, _, argument = text.partition(" ")
    if command == "/remember":
        key = await runtime.memory.remember("owner", argument)
        print(f"Preferência salva: {key[:12]}")
    elif command == "/forget":
        if await console_input("Apagar todas as preferências persistidas? Digite APAGAR: ") == "APAGAR":
            await runtime.memory.forget("owner")
            print("Preferências removidas.")
    elif command == "/clear":
        await runtime.agent.clear("owner", session)
        print("Conversa limpa; ações pendentes revogadas.")
    elif command == "/confirm":
        result = await runtime.home.confirm(argument.strip(), "owner", session)
        print(result["message"])
    elif command == "/help":
        print("/remember TEXTO | /forget | /clear | /confirm TOKEN | /exit")
    elif text.startswith("/"):
        print("Comando desconhecido. Digite /help.")
    else:
        return False
    return True


async def run_console(settings: Settings, voice: bool) -> None:
    """Listen, transcribe, reason and play sequentially to avoid hearing our own speech."""
    from app.exceptions import JarvisError
    from app.runtime import Runtime

    runtime = await Runtime.create(settings)
    try:
        if voice:
            await runtime.enable_audio()
        print("J.A.R.V.I.S. pronto. Ctrl+C encerra. Modo texto: /help para comandos.")
        session = "desktop"
        while True:
            try:
                if voice:
                    print("Ouvindo…")
                    audio = await runtime.recorder.record()
                    if audio is None:
                        continue
                    async with asyncio.timeout(settings.turn_timeout):
                        text = await runtime.stt.transcribe(audio)
                    if not text:
                        continue
                    print("Você: " + terminal_text(text))
                else:
                    text = (await console_input("Você: ")).strip()
                    if text == "/exit":
                        break
                    if not text:
                        continue
                    if await handle_command(runtime, text, session):
                        continue
                response = await runtime.agent.chat("owner", session, text)
                print("J.A.R.V.I.S.: " + terminal_text(response.text))
                for warning in response.warnings:
                    print("Aviso: " + warning)
                for pending in response.pending_actions:
                    print(f"Ação pendente: {terminal_text(pending['description'])}")
                    print(f"Confirmação: /confirm {pending['token']} (expira em {pending['expires_in_seconds']}s)")
                if voice:
                    try:
                        await runtime.player.play(await runtime.tts.synthesize(response.text))
                    except JarvisError as exc:
                        print(str(exc), file=sys.stderr)
                    for pending in response.pending_actions:
                        answer = await console_input(f"Executar '{terminal_text(pending['description'])}'? Digite CONFIRMAR (Enter cancela): ")
                        if answer == "/exit":
                            return
                        if answer == "CONFIRMAR":
                            result = await runtime.home.confirm(pending["token"], "owner", session)
                            print(result["message"])
            except (JarvisError, ValueError, TimeoutError) as exc:
                print(terminal_text(str(exc)) or "Tempo de operação excedido.", file=sys.stderr)
                if voice:
                    await asyncio.sleep(1)
    finally:
        await runtime.aclose()


def main() -> None:
    """Parse options before constructing any expensive service."""
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. — assistente pessoal")
    parser.add_argument("--mode", choices=("voice", "text", "api", "hybrid"), default="voice")
    parser.add_argument("--list-devices", action="store_true", help="Listar dispositivos de áudio e sair")
    parser.add_argument("--hybrid-host", default="127.0.0.1")
    parser.add_argument("--hybrid-port", type=int, default=8000)
    args = parser.parse_args()
    if args.mode == "hybrid":
        if args.list_devices:
            parser.error("--list-devices não se aplica ao modo hybrid")
        from app.hybrid_launcher import launch

        raise SystemExit(launch(host=args.hybrid_host, port=args.hybrid_port))

    import structlog
    from pydantic import ValidationError

    from app.config import Settings
    from app.exceptions import JarvisError
    from app.logging_config import configure_logging

    logger = structlog.get_logger()
    try:
        if args.list_devices:
            import sounddevice as sd

            print(sd.query_devices())
            return
        settings = Settings()
        configure_logging(settings.log_level)
        if args.mode == "api":
            import uvicorn

            from app.api.server import create_app

            uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port,
                        workers=1, access_log=False, limit_concurrency=16)
        else:
            asyncio.run(run_console(settings, voice=args.mode == "voice"))
    except KeyboardInterrupt:
        print("\nJ.A.R.V.I.S. encerrado.")
    except ValidationError as exc:
        # Never render Pydantic's default error, which includes raw environment secrets.
        fields = ", ".join(".".join(map(str, e["loc"])) or "configuração" for e in exc.errors())
        print(f"Configuração inválida: {fields}. Revise .env.example.", file=sys.stderr)
        raise SystemExit(2) from None
    except JarvisError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        logger.error("startup_failed", error_type=type(exc).__name__)
        print("Falha na inicialização. Verifique dependências e configuração; consulte README.md.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
