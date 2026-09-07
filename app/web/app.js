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
}
async function status() {
  const current = epoch;
  try {
    const data = await api('/system/status'); if (current !== epoch) return;
    catalog = data.provider === 'omniroute' ? (data.models || []) : []; renderCatalog();
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
  epoch++; token = ''; catalog = []; renderCatalog(); session = crypto.randomUUID(); turns = 0;
  $('turns').textContent = '0 respostas'; $('messages').replaceChildren(); $('pending').replaceChildren(); $('events').replaceChildren();
  $('model').textContent = 'Aguardando conexão'; $('provider').textContent = 'Não consultado';
  $('memory-status').textContent = 'Não consultada'; $('core-state').textContent = 'DESCONECTADO';
  $('home').textContent = 'Conecte-se para consultar.'; if ('speechSynthesis' in window) speechSynthesis.cancel();
  event('Desconectado. Uma requisição já enviada pode terminar no servidor.');
});
$('refresh').addEventListener('click', status);
$('chat-form').addEventListener('submit', async e => {
  e.preventDefault(); if (busy) return;
  const text = $('prompt').value.trim(); if (!text) return;
  if (!token) return notice('Conecte-se antes de enviar.');
  const current = epoch; busy = true; $('send').disabled = true; $('clear').disabled = true;
  $('chat-state').textContent = 'Processando o pedido…'; $('prompt').value = '';
  bubble(text, 'user');
  try {
    const data = await api('/chat', 'POST', {message: text, session_id: session});
    if (current !== epoch) return;
    bubble(data.text); turns++; $('turns').textContent = `${turns} respostas`;
    data.warnings.forEach(event); event('Resposta recebida.');
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
  } catch (error) { if (current === epoch) { bubble(error.message, 'assistant', true); event(error.message); } }
  finally { busy = false; $('send').disabled = false; $('clear').disabled = false; $('chat-state').textContent = 'Enter envia · Shift + Enter quebra a linha'; }
});
$('prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chat-form').requestSubmit(); } });
$('clear').addEventListener('click', async () => {
  if (busy || !confirm('Limpar a conversa atual e revogar ações pendentes?')) return;
  try { await api(`/sessions/${session}`, 'DELETE'); $('messages').replaceChildren(); $('pending').replaceChildren(); turns = 0; $('turns').textContent = '0 respostas'; event('Conversa limpa. Preferências persistentes mantidas.'); } catch (error) { event(error.message); }
});
$('memory-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.currentTarget.querySelector('button'); button.disabled = true;
  try { await api('/memory', 'POST', {text: $('preference').value}); $('preference').value = ''; event('Preferência salva na memória persistente.'); } catch (error) { event(error.message); } finally { button.disabled = false; }
});
$('forget').addEventListener('click', async () => {
  if (!confirm('Apagar todas as preferências persistidas? Esta ação não pode ser desfeita.')) return;
  try { await api('/memory', 'DELETE'); event('Preferências apagadas. Limpe também a conversa se quiser remover seu contexto atual.'); } catch (error) { event(error.message); }
});
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
  const recognition = new Recognition(); recognition.lang = 'pt-BR'; recognition.interimResults = false;
  recognition.onresult = e => { $('prompt').value = e.results[0][0].transcript; notice('Transcrição pronta. Revise e envie.'); };
  recognition.onerror = () => notice('Microfone indisponível ou reconhecimento recusado. Confira a permissão do navegador.');
  recognition.onend = () => { $('mic').disabled = false; $('mic').textContent = '◎ Ditar mensagem'; };
  $('mic').addEventListener('click', () => {
    if (!confirm('Usar reconhecimento de voz do navegador? Dependendo do navegador, o áudio pode ser processado online.')) return;
    try { if ('speechSynthesis' in window) speechSynthesis.cancel(); recognition.start(); $('mic').disabled = true; $('mic').textContent = 'Ouvindo…'; } catch { notice('Não foi possível iniciar o microfone.'); }
  });
} else { $('mic').disabled = true; $('mic').textContent = 'Ditado não suportado'; }
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
