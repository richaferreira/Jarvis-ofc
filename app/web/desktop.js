'use strict';
let sharedScreen=null, visionTimer=null, visionBusy=false, visionRequest=null;
function stopScreen(){
  clearTimeout(visionTimer);visionTimer=null;$('live-screen').checked=false;
  sharedScreen?.getTracks().forEach(track=>track.stop());sharedScreen=null;
  $('screen-preview').srcObject=null;visionRequest?.abort();notice('Captura encerrada.');
}
$('share-screen').addEventListener('click',async()=>{
  if(!token)return notice('Conecte-se antes de compartilhar.');
  if(!navigator.mediaDevices?.getDisplayMedia)return notice('Captura de tela não suportada neste navegador. Use Chrome/Edge desktop em localhost.');
  try {
    stopScreen();sharedScreen=await navigator.mediaDevices.getDisplayMedia({video:true,audio:false});
    $('screen-preview').srcObject=sharedScreen;
    sharedScreen.getVideoTracks()[0].addEventListener('ended',stopScreen,{once:true});
    notice('Tela selecionada. Clique em Analisar captura para enviar uma imagem ao modelo.');
  }catch{notice('Captura não iniciada ou permissão recusada.');}
});
async function analyzeScreen(){
  if(visionBusy)return;
  if(!token)return notice('Conecte-se primeiro.');
  let image='';const video=$('screen-preview');
  if(sharedScreen && video.videoWidth){
    const canvas=document.createElement('canvas'),scale=Math.min(1,1280/video.videoWidth,800/video.videoHeight);
    canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
    canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);image=canvas.toDataURL('image/jpeg',.75);
  }
  const text=$('debug-text').value.trim();
  if(!image&&!text)return notice('Escolha uma tela ou cole um traceback.');
  visionBusy=true;visionRequest=new AbortController();$('analyze-screen').disabled=true;
  notice('Analisando. O tempo depende do modelo e da conexão.');
  try{
    const response=await fetch('/vision',{method:'POST',headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json'},
      body:JSON.stringify({image,text:text||'Explique o que aparece nesta tela.',debugger:$('debug-screen').checked,model:$('model-select').value||null}),signal:visionRequest.signal});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Falha na análise.');
    $('vision-result').textContent=data.text;event('Análise de tela/traceback concluída.');
  }catch(error){if(error.name!=='AbortError')event(error.message);}
  finally{visionBusy=false;visionRequest=null;$('analyze-screen').disabled=false;
    if($('live-screen').checked&&sharedScreen)visionTimer=setTimeout(analyzeScreen,15000);
  }
}
$('analyze-screen').addEventListener('click',()=>{clearTimeout(visionTimer);analyzeScreen();});
$('live-screen').addEventListener('change',()=>{
  clearTimeout(visionTimer);
  if(!$('live-screen').checked)return;
  if(!sharedScreen){$('live-screen').checked=false;return notice('Escolha primeiro a tela a compartilhar.');}
  if(!confirm('Enviar capturas ao modelo continuamente, com intervalo de 15 segundos após cada resposta? Isso pode consumir sua cota de API.')){$('live-screen').checked=false;return;}
  analyzeScreen();
});
$('stop-screen').addEventListener('click',stopScreen);
document.addEventListener('jarvis-disconnected',()=>{stopScreen();$('vision-result').textContent='';$('knowledge-list').replaceChildren();$('desktop-plan').replaceChildren();});
async function loadKnowledge(){
  try{const entries=await api('/knowledge');$('knowledge-list').replaceChildren();
    for(const entry of entries.reverse()){
      const row=document.createElement('article'),title=document.createElement('b'),text=document.createElement('p'),button=document.createElement('button');
      title.textContent=({preference:'Preferência',code_tip:'Dica de código',resolved_error:'Erro resolvido'})[entry.category]||entry.category;
      text.textContent=entry.text;button.textContent='Excluir';
      button.addEventListener('click',async()=>{if(!confirm('Excluir este conhecimento?'))return;try{await api('/knowledge/'+entry.id,'DELETE');await loadKnowledge();}catch(error){event(error.message);}});
      row.append(title,text,button);$('knowledge-list').append(row);
    }
  }catch(error){notice(error.message);}
}
$('save-knowledge').addEventListener('click',async()=>{
  const text=$('knowledge-text').value.trim();if(!text)return;
  try{await api('/knowledge','POST',{category:$('knowledge-category').value,text});$('knowledge-text').value='';await loadKnowledge();event('Conhecimento salvo em JSON.');}catch(error){event(error.message);}
});
$('save-debug').addEventListener('click',()=>{
  if(!$('vision-result').textContent)return notice('Faça uma análise primeiro.');
  $('knowledge-category').value='resolved_error';$('knowledge-text').value=$('vision-result').textContent.slice(0,4000);
  $('knowledge').scrollIntoView();notice('Revise a análise e salve somente após confirmar que o erro foi resolvido.');
});
async function loadDesktop(discover=false){
  try{const config=await api(discover?'/desktop/discover':'/desktop/config');$('desktop-config').value=JSON.stringify(config,null,2);}catch(error){event(error.message);}
}
$('load-desktop').addEventListener('click',()=>loadDesktop());
$('discover-apps').addEventListener('click',()=>loadDesktop(true));
$('save-desktop').addEventListener('click',async()=>{
  try{await api('/desktop/config','PUT',JSON.parse($('desktop-config').value));event('Perfis e repositórios cadastrados.');}catch(error){event(error.message);}
});
$('desktop-review').addEventListener('click',async()=>{
  try{const plan=await api('/desktop/propose','POST',{action:$('desktop-action').value,alias:$('desktop-alias').value.trim(),
    paths:$('git-paths').value.split('\n').map(x=>x.trim()).filter(Boolean),message:$('git-message').value,session_id:session});
    const container=$('desktop-plan');container.replaceChildren();const description=document.createElement('p'),detail=document.createElement('pre'),button=document.createElement('button');
    description.textContent=plan.description;detail.textContent=plan.detail||'Confira o perfil antes de executar. O fechamento pode pedir para salvar documentos.';button.textContent='Confirmar operação revisada';
    const plannedSession=session;
    button.addEventListener('click',async()=>{if(session!==plannedSession)return notice('A conversa mudou. Crie nova revisão.');button.disabled=true;
      try{const result=await api('/desktop/confirm','POST',{token:plan.token,session_id:plannedSession});event(result.message);container.replaceChildren();}catch(error){event(error.message);}
    });container.append(description,detail,button);
  }catch(error){event(error.message);}
});
document.addEventListener('jarvis-connected',loadKnowledge);

window.addEventListener('pagehide',()=>{stopScreen();voiceActive=false;recognition?.stop();stopResponse();});
