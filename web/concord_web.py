#!/usr/bin/env python3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
STATE_FILE='/home/pi/concord_state.json'; PORT=8080
HTML=r'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Concord Home Security</title><style>
body{font-family:Arial,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f3f4f6;color:#111827}h1{margin:0 0 4px}.subtle{color:#6b7280}.panel{padding:18px;border-radius:12px;background:white;margin:14px 0}.panel-top{display:flex;gap:14px;justify-content:space-between;flex-wrap:wrap}.big-status{font-size:28px;font-weight:700}.badge{display:inline-block;padding:6px 10px;border-radius:999px;font-weight:700}.good{background:#dcfce7;color:#166534}.warn{background:#fef3c7;color:#92400e}.bad{background:#fee2e2;color:#991b1b}.neutral{background:#e5e7eb;color:#374151}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.zone{background:white;padding:14px;border-radius:10px;border-left:5px solid #9ca3af}.zone.closed{border-left-color:#22c55e}.zone.open{border-left-color:#ef4444}.zone.alarm,.zone.faulted,.zone.trouble{border-left-color:#dc2626}.zone.bypassed{border-left-color:#f59e0b}.zone-name{font-weight:700;font-size:17px}.zone-meta{color:#6b7280;font-size:13px;margin-top:4px}.zone-state{margin-top:8px;font-weight:700}.alert{padding:10px;border-radius:8px;background:#fee2e2;margin-bottom:8px}.history-row{padding:8px 0;border-bottom:1px solid #e5e7eb;font-size:14px}.touchpad{font-family:monospace;background:#111827;color:#86efac;padding:14px;border-radius:8px;white-space:pre-line}.section-title{margin-top:0}</style></head><body>
<h1>Concord Home Security</h1><div id="connection" class="subtle">Connecting...</div>
<div class="panel"><div class="panel-top">
<div><div class="subtle">System</div><div id="armMode" class="big-status">UNKNOWN</div></div>
<div><div class="subtle">Perimeter</div><div id="readyState" class="badge neutral">UNKNOWN</div></div>
<div><div class="subtle">Chime</div><div id="chimeState" class="badge neutral">UNKNOWN</div></div>
<div><div class="subtle">Panel</div><div id="panelState" class="badge neutral">UNKNOWN</div></div>
<div><div class="subtle">Active alerts</div><div id="alertCount" class="big-status">0</div></div>
</div></div>
<div id="alertsPanel" class="panel" style="display:none"><h2 class="section-title">Active Alerts</h2><div id="alerts"></div></div>
<div class="panel"><h2 class="section-title">Zones</h2><div id="zones" class="grid"></div></div>
<div id="touchpadPanel" class="panel" style="display:none"><h2 class="section-title">Keypad Display</h2><div id="touchpad" class="touchpad"></div></div>
<div class="panel"><h2 class="section-title">Recent Events</h2><div id="history"></div></div>
<script>
function esc(v){const d=document.createElement('div');d.textContent=v==null?'':String(v);return d.innerHTML}function arm(m){const x={disarmed:'DISARMED',armed_stay:'ARMED STAY',armed_away:'ARMED AWAY',armed_night:'ARMED NIGHT',armed_silent:'ARMED SILENT',zone_test:'ZONE TEST',phone_test:'PHONE TEST',sensor_test:'SENSOR TEST'};return x[m]||String(m||'unknown').toUpperCase()}
async function update(){try{const r=await fetch('/api/status?ts='+Date.now(),{cache:'no-store'});const d=await r.json(),p=d.panel||{},z=d.zones||{},a=d.alerts||[],h=d.history||[],t=d.touchpad||{};document.getElementById('connection').textContent='Live connection active • '+((d.system||{}).updated||'');document.getElementById('armMode').textContent=arm(p.arm_mode);

const rs=document.getElementById('readyState');
const perimeterZones=['3','4','5','7','8'];
const openPerimeter=perimeterZones.filter(k =>
    z[k] && ['open','alarm','faulted','trouble'].includes(z[k].state)
);

if(openPerimeter.length===0){
    rs.textContent='CLEAR';
    rs.className='badge good';
}else{
    rs.textContent='NOT READY';
    rs.className='badge bad';
}

const cs=document.getElementById('chimeState');
const partitions=d.partitions||{};

let chimeText='';

if(t['1'] && t['1'].full_text){
    chimeText += ' ' + String(t['1'].full_text);
}

if(partitions['1'] && partitions['1'].display_text){
    chimeText += ' ' + String(partitions['1'].display_text);
}

chimeText=chimeText.toUpperCase();

if(chimeText.indexOf('CHIME IS ON')>=0){
    cs.textContent='ON';
    cs.className='badge good';
}else if(chimeText.indexOf('CHIME IS OFF')>=0){
    cs.textContent='OFF';
    cs.className='badge neutral';
}else{
    cs.textContent='UNKNOWN';
    cs.className='badge neutral';
}

const ps=document.getElementById('panelState');ps.textContent=String(p.state||p.connection||'unknown').toUpperCase();ps.className='badge '+((p.state==='active'||p.connection==='connected')?'good':(p.state==='alarm'||p.connection==='faulted')?'bad':'warn');document.getElementById('alertCount').textContent=a.length;const ap=document.getElementById('alertsPanel'),ad=document.getElementById('alerts');ad.innerHTML='';if(a.length){ap.style.display='block';a.slice(0,10).forEach(x=>{const q=document.createElement('div');q.className='alert';q.innerHTML='<strong>'+esc(x.name||x.description||x.type)+'</strong><div>'+esc(x.state||x.description||'')+'</div><div class="subtle">'+esc(x.time||'')+'</div>';ad.appendChild(q)})}else ap.style.display='none';const zd=document.getElementById('zones');zd.innerHTML='';Object.keys(z).filter(k=>k!=='88').sort((x,y)=>Number(x)-Number(y)).forEach(k=>{const x=z[k],q=document.createElement('div');q.className='zone '+esc(x.state||'unknown');q.innerHTML='<div class="zone-name">'+esc(x.name||('Zone '+k))+'</div><div class="zone-meta">Zone '+esc(k)+' • Partition '+esc(x.partition||1)+'</div><div class="zone-state">'+esc(String(x.state||'unknown').toUpperCase())+'</div>';zd.appendChild(q)});const tp=document.getElementById('touchpadPanel'),td=document.getElementById('touchpad'),ks=Object.keys(t);if(ks.length){const x=t['1']||t[ks[0]];td.textContent=(x.line1||'')+'\n'+(x.line2||'');tp.style.display='block'}else tp.style.display='none';const hd=document.getElementById('history');hd.innerHTML='';h.slice(0,20).forEach(x=>{const q=document.createElement('div');q.className='history-row';q.innerHTML='<strong>'+esc(x.message||x.type)+'</strong><div class="subtle">'+esc(x.time||'')+'</div>';hd.appendChild(q)})}catch(e){document.getElementById('connection').textContent='Dashboard cannot read Concord state'}}update();setInterval(update,1000);
</script></body></html>'''
class H(BaseHTTPRequestHandler):
    def send_headers(self,ctype):
        self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Cache-Control','no-store, no-cache, must-revalidate'); self.send_header('Pragma','no-cache'); self.end_headers()
    def do_GET(self):
        if self.path.startswith('/api/status'):
            try:
                with open(STATE_FILE) as f: data=json.load(f)
                self.send_headers('application/json'); self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
        else:
            self.send_headers('text/html; charset=utf-8'); self.wfile.write(HTML.encode())
    def log_message(self,format,*args): return
HTTPServer(('0.0.0.0',PORT),H).serve_forever()

