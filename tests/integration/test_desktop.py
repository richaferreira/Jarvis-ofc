import asyncio
import base64
import io
import json
import subprocess

import httpx
import pytest
from PIL import Image

from app.api.browser_session import BrowserSessions
from app.api.desktop_routes import validate_image
from app.api.server import create_app
from app.desktop.service import DesktopService
from app.exceptions import JarvisError
from app.memory.knowledge import KnowledgeStore


async def test_json_memory_is_atomic_persistent_and_owner_scoped(tmp_path):
    first, second = KnowledgeStore(tmp_path), KnowledgeStore(tmp_path)
    await asyncio.gather(first.save('owner','code_tip','Use asyncio para I/O.'),
                         second.save('owner','resolved_error','NameError: defina a variável.'))
    assert len(await first.list_entries('owner')) == 2
    assert await first.list_entries('other') == []
    assert len(json.loads((tmp_path/'knowledge.json').read_text())) == 2
    entries = await second.list_entries('owner')
    await first.delete('other', entries[0]['id'])
    assert len(await first.list_entries('owner')) == 2
    await first.delete('owner', entries[0]['id'])
    assert len(await first.list_entries('owner')) == 1
    (tmp_path/'knowledge.json').write_text('broken json')
    with pytest.raises(JarvisError):
        await first.save('owner','preference','Do not overwrite corrupt JSON')
    assert (tmp_path/'knowledge.json').read_text() == 'broken json'


async def test_remembered_session_refresh_and_logout(settings):
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        headers = {'Authorization':'Bearer '+settings.api_token.get_secret_value(), 'X-Jarvis-Request':'1', 'Origin':'http://test'}
        response = await client.post('/session/login',headers=headers)
        assert response.status_code == 200
        access = response.json()['access_token']
        assert access != settings.api_token.get_secret_value()
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'Path=/session' in response.headers['set-cookie']
        assert await BrowserSessions(settings.data_dir, settings.api_token.get_secret_value()).valid(access)
        assert (await client.post('/session/refresh',headers={'X-Jarvis-Request':'1','Origin':'http://evil'})).status_code == 403
        assert (await client.post('/session/refresh',headers={'X-Jarvis-Request':'1'})).json()['access_token'] == access
        assert (await client.get('/knowledge',headers={'Authorization':'Bearer '+access})).status_code == 200
        await client.post('/session/logout',headers={'X-Jarvis-Request':'1'})
        assert (await client.get('/knowledge',headers={'Authorization':'Bearer '+access})).status_code == 401
        assert (await client.post('/session/refresh',headers={'X-Jarvis-Request':'1'})).status_code == 401


def test_image_validation_resizes_and_rejects_non_images():
    output=io.BytesIO()
    Image.new('RGB',(2000,1000)).save(output,format='PNG')
    encoded='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
    result=validate_image(encoded)
    with Image.open(io.BytesIO(base64.b64decode(result.split(',')[1]))) as image:
        assert image.width <= 1600
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        validate_image('data:image/jpeg;base64,not-valid')


async def test_git_reviews_reject_changes_replay_and_paths(tmp_path):
    repo=tmp_path/'repo'
    repo.mkdir()
    subprocess.run(['git','init',str(repo)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'config','user.name','Test'],check=True)
    subprocess.run(['git','-C',str(repo),'config','user.email','test@example.invalid'],check=True)
    service=DesktopService(tmp_path/'data')
    service.path.parent.mkdir()
    service.path.write_text(json.dumps({'apps':{},'profiles':{},'repos':{'test':str(repo)}}))
    (repo/'app.py').write_text('print(1)\n')
    plan=await service.propose('owner','session','git_add','test',['app.py'],'')
    with pytest.raises(JarvisError):
        await service.confirm('other','session',plan['token'])
    (repo/'app.py').write_text('print(2)\n')
    with pytest.raises(JarvisError,match='mudaram'):
        await service.confirm('owner','session',plan['token'])
    plan=await service.propose('owner','session','git_add','test',['app.py'],'')
    await service.confirm('owner','session',plan['token'])
    with pytest.raises(JarvisError):
        await service.confirm('owner','session',plan['token'])
    commit=await service.propose('owner','session','git_commit','test',[],'Add app')
    await service.confirm('owner','session',commit['token'])
    assert (await service.command(repo,'log','-1','--format=%s')).strip() == 'Add app'
    for path in ['../outside.txt','.env','.git/config']:
        with pytest.raises(JarvisError):
            await service.propose('owner','session','git_add','test',[path],'')
