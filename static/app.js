const $ = (s) => document.querySelector(s);
const navs = document.querySelectorAll('.nav');
const sections = document.querySelectorAll('.section');
const historyKey = 'agroguard-history-v1';

function showSection(id){
  sections.forEach(s=>s.classList.toggle('active',s.id===id));
  navs.forEach(n=>n.classList.toggle('active',n.dataset.section===id));
  window.scrollTo({top:0,behavior:'smooth'});
  if(id==='history') renderHistory();
  if(id==='risk') loadWeather();
}
navs.forEach(n=>n.addEventListener('click',()=>showSection(n.dataset.section)));
$('#startScan').addEventListener('click',()=>showSection('scanner'));

const drop = $('#dropZone'), input = $('#fileInput'), preview = $('#preview');
$('#chooseFile').addEventListener('click',e=>{e.stopPropagation();input.click()});
drop.addEventListener('click',()=>input.click());
input.addEventListener('change',()=>setFile(input.files[0]));
['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('drag')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('drag')}));
drop.addEventListener('drop',e=>setFile(e.dataTransfer.files[0]));
function setFile(file){
  if(!file)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){alert('Please select JPG, PNG or WEBP.');return}
  if(file.size>8*1024*1024){alert('Maximum image size is 8MB.');return}
  const url=URL.createObjectURL(file); preview.src=url; preview.hidden=false;
  drop.querySelector('.upload-icon').style.display='none'; drop.querySelector('h3').textContent=file.name; drop.querySelector('p').textContent='Ready for AI analysis';
}

$('#analyse').addEventListener('click',async()=>{
  const file=input.files[0];
  if(!file){alert('Upload a crop image first.');return}
  const btn=$('#analyse'); btn.disabled=true; btn.textContent='Analyzing image…';
  $('#emptyState').hidden=false; $('#results').hidden=true; $('#emptyState').innerHTML='<div class="empty-icon">◌</div><h3>AI is inspecting the crop…</h3><p>Checking visible symptoms, disease likelihood and safe next steps.</p>';
  const fd=new FormData(); fd.append('image',file); fd.append('crop',$('#crop').value);
  try{
    const r=await fetch('/api/diagnose',{method:'POST',body:fd});
    const data=await r.json(); if(!r.ok) throw new Error(data.error||'Diagnosis failed');
    renderResult(data); saveHistory(data);
  }catch(e){
    $('#emptyState').innerHTML='<div class="empty-icon">!</div><h3>Analysis failed</h3><p>'+escapeHtml(e.message)+'</p>';
  }finally{btn.disabled=false;btn.textContent='Analyze Crop with AI'}
});

function renderResult(d){
  $('#emptyState').hidden=true;
  const r=$('#results'); r.hidden=false;
  const confidence=Number(d.confidence||0);
  const escalation=confidence<60 || /unclear|unknown|api key/i.test(d.disease||'');
  r.innerHTML=`
    <div class="result-top"><div><div class="eyebrow">AI DIAGNOSIS · ${escapeHtml(d.crop||'Crop')}</div><h3 class="result-title">${escapeHtml(d.disease||'Unclear')}</h3><div class="result-status">${escapeHtml(d.status||'')}</div></div><div class="confidence"><strong>${confidence}%</strong><small>AI confidence</small></div></div>
    <div style="margin-top:12px"><span class="severity ${escapeHtml(d.severity||'Unknown')}">${escapeHtml(d.severity||'Unknown')} severity</span>${d.pest&&d.pest!=='None/Unknown'?` <span class="severity">Pest: ${escapeHtml(d.pest)}</span>`:''}</div>
    <div class="result-grid">
      <div class="result-box"><h4>Visible symptoms</h4><ul>${list(d.symptoms)}</ul></div>
      <div class="result-box"><h4>Action plan · IPM first</h4><ul>${list(d.actions)}</ul></div>
      <div class="result-box"><h4>Prevention</h4><ul>${list(d.prevention)}</ul></div>
      <div class="result-box"><h4>AI notes</h4><p class="notes">${escapeHtml(d.notes||'')}</p></div>
    </div>
    ${escalation?'<div class="escalate"><b>Expert verification recommended.</b> This case is low-confidence or unclear. Do not make a pesticide decision from this screen alone; route the case to an agronomist/KVK expert.</div>':''}
    <div class="report-actions"><button class="secondary report-btn" id="downloadReport">⬇ Download PDF Report</button><span class="report-hint">Includes diagnosis, image, symptoms, actions & prevention</span></div>
    <div class="result-meta">Mode: ${escapeHtml(d.mode||'AI')} · ${escapeHtml(d.timestamp||new Date().toLocaleString())}</div>`;
  $('#downloadReport').addEventListener('click',()=>downloadReport(d));
}

async function downloadReport(d){
  const btn=$('#downloadReport');
  const file=input.files[0];
  if(!file){alert('Please keep the analyzed image selected before downloading the report.');return}
  btn.disabled=true; btn.textContent='Preparing PDF…';
  try{
    const fd=new FormData();
    fd.append('image',file);
    fd.append('result',JSON.stringify(d));
    const r=await fetch('/api/report',{method:'POST',body:fd});
    if(!r.ok){
      let msg='Could not generate PDF report.';
      try{const x=await r.json(); msg=x.error||msg}catch(_){}
      throw new Error(msg);
    }
    const blob=await r.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url; a.download='AgroGuard_AI_Crop_Report.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){alert(e.message)}
  finally{btn.disabled=false; btn.textContent='⬇ Download PDF Report'}
}

function list(a){return (Array.isArray(a)&&a.length?a:['No information returned.']).map(x=>`<li>${escapeHtml(String(x))}</li>`).join('')}
function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}

function saveHistory(d){
  const h=JSON.parse(localStorage.getItem(historyKey)||'[]'); h.unshift({crop:d.crop,disease:d.disease,confidence:d.confidence,severity:d.severity,timestamp:d.timestamp||new Date().toISOString()}); localStorage.setItem(historyKey,JSON.stringify(h.slice(0,12)));
}
function renderHistory(){
  const h=JSON.parse(localStorage.getItem(historyKey)||'[]'); const el=$('#historyList');
  if(!h.length){el.innerHTML='<div class="result-empty" style="min-height:260px;background:#fff;border:1px solid var(--line);border-radius:14px"><div class="empty-icon">⌁</div><h3>No previous scans found.</h3><p>Run your first crop scan from the AI Scanner.</p></div>';return}
  el.innerHTML=h.map(x=>`<div class="history-item"><div><b>${escapeHtml(x.disease)}</b><div style="font-size:10px;color:#7b838d;margin-top:5px">${escapeHtml(x.crop)} · ${escapeHtml(x.severity||'Unknown')} · ${escapeHtml(x.confidence||0)}% confidence</div></div><div class="date">${new Date(x.timestamp).toLocaleString()}</div></div>`).join('');
}
$('#clearHistory').addEventListener('click',()=>{localStorage.removeItem(historyKey);renderHistory()});

async function loadWeather(lat=28.6139,lon=77.2090){
  $('#riskNote').textContent='Fetching live weather…';
  try{const r=await fetch(`/api/weather?lat=${lat}&lon=${lon}`);const d=await r.json(); if(d.error)throw new Error(d.error);
    $('#riskScore').textContent=d.risk==null?'--':d.risk; $('#riskLabel').textContent=d.label; $('#riskNote').textContent=d.note||'';
    const items=[['Temperature',d.temperature,'°C'],['Humidity',d.humidity,'%'],['Rain',d.rain,'mm'],['Wind',d.wind,'km/h']];
    $('#weatherCards').innerHTML=items.map(i=>`<div class="weather-card"><div class="label">${i[0]}</div><div class="value">${i[1]??'--'} <span class="unit">${i[2]}</span></div></div>`).join('');
  }catch(e){$('#riskNote').textContent='Weather service unavailable: '+e.message}
}
$('#locate').addEventListener('click',()=>{if(!navigator.geolocation){alert('Geolocation is not supported.');return} navigator.geolocation.getCurrentPosition(p=>loadWeather(p.coords.latitude,p.coords.longitude),()=>alert('Location permission denied; showing default region.'))});

fetch('/api/health').then(r=>r.json()).then(d=>$('#aiState').textContent=d.ai_configured?'Ready':'Key required').catch(()=>$('#aiState').textContent='Offline');
renderHistory();
