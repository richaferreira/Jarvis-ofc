"""Allowlisted desktop profiles and reviewable Git changes. Never run model shell text."""
import asyncio
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from app.exceptions import JarvisError


class DesktopService:
    def __init__(self, directory: Path) -> None:
        self.path = directory / 'desktop.json'
        self.pending: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    def config(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({'apps': {}, 'profiles': {'gamer': [], 'produtividade': []},
                                            'repos': {'jarvis': str(Path.cwd())}}, indent=2), encoding='utf-8')
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise JarvisError('Revise data/desktop.json; configuração não foi modificada.') from exc

    async def command(self, repo: Path, *args: str) -> str:
        env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_PAGER': 'cat'}
        process = await asyncio.create_subprocess_exec('git', '--no-pager', *args, cwd=repo,
                    env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            async with asyncio.timeout(20):
                output, error = await process.communicate()
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise JarvisError('Git recusou a operação. Confira o repositório, a identidade Git e eventuais hooks no terminal.')
        if len(output) > 2_000_000:
            raise JarvisError('Resultado Git muito grande. Selecione uma alteração menor.')
        return output.decode('utf-8', errors='replace')

    def repo(self, alias: str) -> Path:
        value = self.config().get('repos', {}).get(alias)
        if not value:
            raise JarvisError('Repositório não cadastrado em desktop.json.')
        root = Path(value).resolve()
        if not (root / '.git').exists():
            raise JarvisError('Cadastre a raiz de um repositório Git.')
        return root

    async def preview(self, action: str, alias: str, paths: list[str], message: str) -> dict[str, Any]:
        config = self.config()
        if action in ('open_profile', 'close_profile'):
            names = config.get('profiles', {}).get(alias)
            if not names:
                raise JarvisError('Perfil vazio ou inexistente. Cadastre os aplicativos em desktop.json.')
            apps = []
            for name in names:
                app = config.get('apps', {}).get(name)
                if not app:
                    raise JarvisError('Aplicativo do perfil não cadastrado.')
                path = Path(os.path.expandvars(app['path'])).resolve()
                if path.suffix.lower() != '.exe' or not path.is_file():
                    raise JarvisError(f'Executável não encontrado: {name}. Revise desktop.json.')
                apps.append({'name': name, 'path': str(path)})
            return {'action': action, 'alias': alias, 'apps': apps,
                    'description': ('Abrir ' if action == 'open_profile' else 'Solicitar fechamento de ') + ', '.join(names)}
        repo = self.repo(alias)
        if action == 'git_add':
            if not paths:
                raise JarvisError('Selecione arquivos específicos para git add.')
            fingerprints = []
            for name in paths:
                path = (repo / name).resolve()
                if not path.is_relative_to(repo) or path.is_relative_to(repo / '.git'):
                    raise JarvisError('Arquivo fora do repositório ou dentro de .git.')
                if path.name == '.env' or path.name.startswith('.env.') and path.name != '.env.example':
                    raise JarvisError('Arquivos de credenciais .env não podem ser adicionados pelo assistente.')
                if path.is_dir() or (path.exists() and path.stat().st_size > 5_000_000):
                    raise JarvisError('Selecione arquivos individuais menores que 5 MB.')
                fingerprints.append(hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else 'deleted')
            detail = await self.command(repo, 'diff', '--stat', '--', *paths)
            return {'action': action, 'alias': alias, 'paths': paths, 'fingerprints': fingerprints,
                    'description': 'git add: ' + ', '.join(paths), 'detail': detail,
                    'repo': str(repo)}
        staged_names = (await self.command(repo, 'diff', '--cached', '--name-only', '-z')).split('\0')
        if any(Path(name).name == '.env' or (Path(name).name.startswith('.env.') and Path(name).name != '.env.example') for name in staged_names):
            raise JarvisError('Há um arquivo .env no stage. Remova-o do stage antes de confirmar pelo assistente.')
        staged = await self.command(repo, 'diff', '--cached', '--stat')
        if not staged.strip() or not message.strip():
            raise JarvisError('Commit exige alterações no stage e uma mensagem.')
        tree = await self.command(repo, 'write-tree')
        head = await self.command(repo, 'status', '--porcelain=v2', '--branch')
        return {'action': action, 'alias': alias, 'message': message, 'tree': tree, 'head': head,
                'description': 'git commit: ' + message, 'detail': staged, 'repo': str(repo)}

    async def propose(self, owner: str, session: str, action: str, alias: str,
                      paths: list[str], message: str) -> dict[str, Any]:
        async with self.lock:
            now = time.monotonic()
            self.pending = {k: v for k, v in self.pending.items() if v['expires'] > now}
            if len(self.pending) >= 32:
                raise JarvisError('Há muitas propostas pendentes. Aguarde a expiração.')
            plan = await self.preview(action, alias, paths, message)
            token = 'desktop_' + secrets.token_urlsafe(24)
            self.pending[token] = dict(owner=owner, session=session, expires=now+120, plan=plan,
                                       args=(action, alias, paths, message))
            return {'status': 'confirmation_required', 'kind': 'desktop', 'token': token,
                    'description': plan['description'], 'detail': plan.get('detail', ''), 'expires_in_seconds': 120}

    async def confirm(self, owner: str, session: str, token: str) -> dict[str, str]:
        async with self.lock:
            item = self.pending.get(token)
            if not item or item['owner'] != owner or item['session'] != session or item['expires'] <= time.monotonic():
                raise JarvisError('Proposta inválida ou expirada. Crie uma nova revisão.')
            del self.pending[token]
            plan = await self.preview(*item['args'])
            if plan != item['plan']:
                raise JarvisError('A configuração ou os arquivos mudaram. Revise uma nova proposta.')
            if plan['action'] == 'git_add':
                await self.command(Path(plan['repo']), '--literal-pathspecs', 'add', '--', *plan['paths'])
            elif plan['action'] == 'git_commit':
                await self.command(Path(plan['repo']), 'commit', '-m', plan['message'])
            else:
                if os.name != 'nt':
                    raise JarvisError('Perfis de aplicativos estão disponíveis no Windows.')
                if plan['action'] == 'open_profile':
                    for app in plan['apps']:
                        await asyncio.create_subprocess_exec(app['path'])
                else:
                    await asyncio.to_thread(self.close_windows, plan['apps'])
            return {'message': 'Operação concluída.' if plan['action'] != 'close_profile' else
                    'Fechamento solicitado às janelas. Aplicativos podem pedir confirmação ou permanecer na bandeja.'}

    async def clear_session(self, owner: str, session: str) -> None:
        async with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if not (v['owner'] == owner and v['session'] == session)}

    @staticmethod
    def close_windows(apps: list[dict[str, str]]) -> None:
        import ctypes
        from ctypes import wintypes
        import psutil
        paths = {os.path.normcase(app['path']) for app in apps}
        pids = set()
        for process in psutil.process_iter(['pid', 'exe']):
            if process.info['exe'] and os.path.normcase(process.info['exe']) in paths:
                pids.add(process.info['pid'])
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        def visit(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE; never terminate unsaved work forcibly.
            return True
        user32.EnumWindows(callback_type(visit), 0)
