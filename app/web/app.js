'use strict';
const $ = id => document.getElementById(id);
let token = '', session = crypto.randomUUID(), busy = false, epoch = 0, turns = 0;
let catalog = [];
function renderCatalog() {
  const term = $('model-filter').value.toLocaleLowerCase('pt-BR');
  $('catalog').replaceChildren();
  const visible = catalog.filter(id => id.toLocaleLowerCase('pt-BR').includes(term));
  if (!visible.length) { const empty=document.createElement('small'); empty.textContent='Nenhum modelo listado. Confira a configuração e consulte o diagnóstico.'; $('catalog').append(empty); }
  for (const id of visible) { const row=document.createElement('div'); row.className='tool'; const name=document.createElement('code'); name.textContent=id; row.append(name); $('catalog').append(row); }
}
$('model-filter').addEventListener('input', renderCatalog);
let activeRequest = null, voiceActive = false, recognition = null;
let zone = 'America/Sao_Paulo';
function notice(text) { $('notice').textContent = text; }
function event(text) {
  const item = document.createElement('li'), time = document.createElement('time');
  time.textContent = new Date().toLocaleTimeString('pt-BR');
  item.append(time, document.createTextNode(text)); $('events').prepend(item);
  while ($('events').children.length > 12) $('events').lastChild.remove();
  notice(text);
}
async function api(path, method = 'GET', body) {
  if (!token) throw new Error('Conecte-se usando o API_TOKEN do seu .env.');
  const response = await fetch(path, {method, headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Requisição recusada. Confira os campos e o token.');
  return data;
}
function bubble(text, role = 'assistant', error = false) {
  $('messages').querySelector('.welcome')?.remove();
  const item = document.createElement('div'); item.className = `bubble ${role}${error ? ' error' : ''}`;
  const label = document.createElement('b'); label.textContent = role === 'user' ? 'VOCÊ' : 'J.A.R.V.I.S.';
  item.append(label, document.createTextNode(text)); $('messages').append(item);
  while ($('messages').children.length > 100) $('messages').firstChild.remove();
  $('messages').scrollTop = $('messages').scrollHeight;
  return item;
}
async function status() {
  const current = epoch;
  try {
    const data = await api('/system/status'); if (current !== epoch) return;
    catalog = data.models || []; renderCatalog();
    const chosen = $('model-select').value; $('model-select').replaceChildren(new Option('Padrão: '+data.model,''));
    for (const id of catalog) $('model-select').add(new Option(id,id));
    if (catalog.includes(chosen)) $('model-select').value = chosen;
    await loadHistory();
    $('model').textContent = data.model; $('provider').textContent = data.provider;
    $('memory-status').textContent = data.memory_enabled ? 'Ativada' : 'Desativada';
    $('prompt').maxLength = data.max_input_chars; zone = data.timezone;
    $('core-state').textContent = data.status === 'available' ? (data.provider === 'omniroute' ? 'GATEWAY ACESSÍVEL' : 'MODELO INSTALADO') : data.status === 'missing_model' ? 'MODELO AUSENTE' : data.status === 'unavailable' ? 'PROVEDOR INDISPONÍVEL' : 'PROVEDOR CONFIGURADO';
    $('home').textContent = data.home_actions.length ? data.home_actions.join(' · ') : 'Nenhuma ação configurada no .env.';
    event(data.message);
  } catch (error) { if (current === epoch) { $('core-state').textContent = 'CONEXÃO NÃO VALIDADA'; event(error.message); } }
}
$('auth').addEventListener('submit', e => { e.preventDefault(); if (busy) return notice('Aguarde a resposta antes de reconectar.'); epoch++; token = $('token').value.trim(); $('token').value = ''; status(); });
$('disconnect').addEventListener('click', () => {
  stopResponse(); voiceActive = false; recognition?.stop(); epoch++; token = ''; catalog = []; renderCatalog(); session = crypto.randomUUID(); turns = 0;
  $('turns').textContent = '0 respostas'; $('messages').replaceChildren(); $('pending').replaceChildren(); $('events').replaceChildren();
  $('model').textContent = 'Aguardando conexão'; $('provider').textContent = 'Não consultado';
  $('memory-status').textContent = 'Não consultada'; $('core-state').textContent = 'DESCONECTADO';
  $('home').textContent = 'Conecte-se para consultar.'; $('history-list').replaceChildren(); $('model-select').replaceChildren(new Option('Padrão do servidor','')); if ('speechSynthesis' in window) speechSynthesis.cancel();
  event('Desconectado. Uma requisição já enviada pode terminar no servidor.');
});
$('refresh').addEventListener('click', status);
$('chat-form').addEventListener('submit', async e => {
  e.preventDefault(); if (busy) return;
  const text = $('prompt').value.trim(); if (!text) return;
  if (!token) return notice('Conecte-se antes de enviar.');
  const current = epoch; busy = true; $('model-select').disabled = true; $('send').disabled = true; $('clear').disabled = true;
  $('chat-state').textContent = 'Processando o pedido…'; $('prompt').value = '';
  bubble(text, 'user');
  try {
    const data = await streamChat(text, current);
    if (current !== epoch) return;
    turns++; $('turns').textContent = `${turns} respostas`;
    data.warnings.forEach(event); event('Resposta recebida.'); await loadHistory();
    if ($('speak').checked && 'speechSynthesis' in window) {
      speechSynthesis.cancel(); const voice = new SpeechSynthesisUtterance(data.text); voice.lang = 'pt-BR'; speechSynthesis.speak(voice);
    }
    $('pending').replaceChildren();
    for (const action of data.pending_actions) {
      const row = document.createElement('p'), button = document.createElement('button');
      row.append(document.createTextNode(`Confirmação necessária: ${action.description}`)); button.textContent = 'Confirmar execução';
      button.addEventListener('click', async () => {
        if (current !== epoch || !confirm(`Executar: ${action.description}?`)) return;
        button.disabled = true;
        try { const result = await api('/actions/confirm', 'POST', {token: action.token, session_id: session}); if (current === epoch) { event(result.message); row.remove(); } }
        catch (error) { if (current === epoch) event(error.message); }
      }); row.append(button); $('pending').append(row);
    }
  } catch (error) { if (current === epoch) { const message = error.name === 'AbortError' ? 'Resposta interrompida.' : error.message; bubble(message, 'assistant', true); event(message); } }
  finally { busy = false; activeRequest = null; $('model-select').disabled = false; $('send').disabled = false; $('clear').disabled = false; $('chat-state').textContent = 'Enter envia · Shift + Enter quebra a linha'; }
});
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chat-form').requestSubmit(); } });
$('clear').addEventListener('click', async () => {
  if (busy || !confirm('Limpar a conversa atual e revogar ações pendentes?')) return;
  try { await api(`/sessions/${session}`, 'DELETE'); $('messages').replaceChildren(); $('pending').replaceChildren(); turns = 0; $('turns').textContent = '0 respostas'; event('Conversa limpa. Preferências persistentes mantidas.'); await loadHistory(); } catch (error) { event(error.message); }
});
$('memory-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.currentTarget.querySelector('button'); button.disabled = true;
  try { await api('/memory', 'POST', {text: $('preference').value}); $('preference').value = ''; event('Preferência salva na memória persistente.'); } catch (error) { event(error.message); } finally { button.disabled = false; }
});
$('forget').addEventListener('click', async () => {
  if (!confirm('Apagar todas as preferências persistidas? Esta ação não pode ser desfeita.')) return;
  try { await api('/memory', 'DELETE'); event('Preferências apagadas. Limpe também a conversa se quiser remover seu contexto atual.'); } catch (error) { event(error.message); }
});
function stopResponse() {
  activeRequest?.abort();
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}
$('stop').addEventListener('click', () => { voiceActive=false; $('continuous').checked=false; recognition?.stop(); stopResponse(); notice('Interrupção solicitada.'); });
$('focus').addEventListener('click', () => document.body.classList.toggle('focus-mode'));
$('new-session').addEventListener('click', () => {
  if(busy) return notice('Interrompa ou aguarde a resposta atual.');
  session=crypto.randomUUID(); turns=0; $('turns').textContent='0 respostas'; $('messages').replaceChildren(); $('pending').replaceChildren(); notice('Nova conversa criada.');
});
async function loadHistory() {
  const current=epoch;
  try {
    const rows=await api('/history'); if(current!==epoch) return;
    $('history-list').replaceChildren();
    for(const row of rows) {
      const button=document.createElement('button'); button.textContent=row.title || 'Conversa';
      button.addEventListener('click',async()=>{
        if(busy) return notice('Interrompa ou aguarde a resposta atual.');
        try { const transcript=await api('/history/'+encodeURIComponent(row.session)); if(current!==epoch || busy) return;
          session=row.session; $('messages').replaceChildren(); $('pending').replaceChildren();
          for(const turn of transcript) {bubble(turn.human,'user');bubble(turn.answer);}
          turns=transcript.length; $('turns').textContent=turns+' respostas';
        } catch(error){event(error.message);}
      }); $('history-list').append(button);
    }
  } catch(error) { if(current===epoch) notice(error.message); }
}
async function streamChat(text,current) {
  activeRequest=new AbortController();
  const response=await fetch('/chat/stream',{method:'POST',headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json'},
    body:JSON.stringify({message:text,session_id:session,model:$('model-select').value || null}),signal:activeRequest.signal});
  if(!response.ok) {const error=await response.json();throw new Error(typeof error.detail==='string'?error.detail:'Pedido recusado.');}
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='',result=null;
  const item=bubble(''),content=document.createElement('span');item.append(content);
  try {
    while(true) {
      const {value,done}=await reader.read();
      pending+=decoder.decode(value || new Uint8Array(),{stream:!done});
      let index;
      while((index=pending.indexOf('\n'))>=0) {
        const line=pending.slice(0,index);pending=pending.slice(index+1);if(!line.trim())continue;
        const message=JSON.parse(line);if(current!==epoch)continue;
        if(message.type==='reset') content.textContent='';
        if(message.type==='token') {content.textContent+=message.text;$('messages').scrollTop=$('messages').scrollHeight;}
        if(message.type==='done') {content.textContent=message.text;result=message;}
        if(message.type==='error') throw new Error(message.message);
      }
      if(pending.length>1000000) throw new Error('Resposta excedeu o limite.');
      if(done)break;
    }
  } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
  if(!result)throw new Error('A transmissão foi interrompida antes de concluir.');
  return result;
}
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
  recognition = new Recognition(); recognition.lang = 'pt-BR'; recognition.interimResults = false;
  recognition.onspeechstart = () => { if(voiceActive) stopResponse(); };
  recognition.onresult = async e => {
    $('prompt').value = e.results[0][0].transcript;
    if($('continuous').checked && voiceActive) {
      for(let i=0;busy && i<40;i++) await new Promise(resolve=>setTimeout(resolve,50));
      if(!busy && voiceActive) $('chat-form').requestSubmit();
    } else notice('Transcrição pronta. Revise e envie.');
  };
  recognition.onerror = e => { if(e.error!=='no-speech') {voiceActive=false;notice('Reconhecimento interrompido. Confira a permissão do microfone.');} };
  recognition.onend = () => {
    $('mic').disabled = false; $('mic').textContent = '◎ Iniciar voz';
    if(voiceActive && $('continuous').checked) setTimeout(()=>{if(voiceActive)try{recognition.start();}catch{voiceActive=false;}},250);
    else voiceActive=false;
  };
  $('mic').addEventListener('click', () => {
    if (!token) return notice('Conecte-se antes de iniciar a voz.');
    if (!confirm('Ativar voz do navegador? O áudio pode ser processado online. Em modo contínuo, as falas serão enviadas automaticamente; use fones para evitar eco.')) return;
    try { stopResponse(); voiceActive=true; recognition.start(); $('mic').textContent='Ouvindo · use Interromper para parar'; } catch { notice('Não foi possível iniciar o microfone.'); }
  });
} else { $('mic').disabled = true; $('continuous').disabled=true; $('mic').textContent = 'Ditado não suportado'; }
if (!('speechSynthesis' in window)) $('speak').disabled = true;
function clock() { const now = new Date(); $('clock').textContent = now.toLocaleTimeString('pt-BR', {timeZone: zone}); $('date').textContent = now.toLocaleDateString('pt-BR', {timeZone: zone, weekday: 'long', day: 'numeric', month: 'long'}); }
clock(); setInterval(clock, 1000);
// Canvas décor is deliberately independent of service-health indicators.
const canvas = $('globe'), ctx = canvas.getContext('2d'), reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
function draw(ms) {
  const w = canvas.clientWidth, h = canvas.clientHeight, dpr = Math.min(devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(w*dpr) || canvas.height !== Math.round(h*dpr)) { canvas.width = Math.round(w*dpr); canvas.height = Math.round(h*dpr); }
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
  const r = Math.min(w*.32,h*.40), angle = reduced ? .3 : ms*.00008;
  const points = [];
  for (let i=0;i<150;i++) { const y=1-2*i/149, a=i*2.399963+angle, c=Math.sqrt(1-y*y); const x=Math.cos(a)*c,z=Math.sin(a)*c; points.push({x:w/2+x*r,y:h/2+y*r,z}); }
  ctx.lineWidth=.5;
  for(let i=0;i<points.length;i++){const p=points[i]; for(let j=i+1;j<points.length;j++){const q=points[j],dist=Math.hypot(p.x-q.x,p.y-q.y); if(dist<r*.29 && Math.abs(p.z-q.z)<.35){ctx.strokeStyle=`rgba(36,185,219,${.06+(p.z+1)*.085})`;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}}ctx.fillStyle=`rgba(89,237,255,${.18+(p.z+1)*.27})`;ctx.beginPath();ctx.arc(p.x,p.y,p.z>0?1.5:1,0,Math.PI*2);ctx.fill();}
  ctx.strokeStyle='#1ec6e733';for(let i=0;i<3;i++){ctx.beginPath();ctx.ellipse(w/2,h/2,r*1.38,r*.32,i*.6-.5,0,Math.PI*2);ctx.stroke();}
  if(!reduced) requestAnimationFrame(draw);
}
if(ctx) draw(0);
