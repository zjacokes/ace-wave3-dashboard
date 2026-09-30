/* File intake and Python runner only. Every result is computed in pipeline.py. */
'use strict';
if (typeof document === 'undefined') {
  // This same file is the worker entry, keeping the app to three source assets.
  let py;
  const ready = (async () => {
    self.postMessage({type:'status', text:'Loading Python runtime…'});
    importScripts('vendor/pyodide/pyodide.js');
    py = await loadPyodide({indexURL:new URL('vendor/pyodide/', self.location.href).href});
    self.postMessage({type:'status', text:'Loading local data tools…'});
    await py.loadPackage('pandas');
    const manifest = await fetch('py/manifest.json').then(r => {if(!r.ok) throw Error('Missing Python manifest'); return r.json();});
    py.FS.mkdirTree('/ace');
    const results = await Promise.allSettled(Object.entries(manifest).map(async ([name, expected]) => {
      const response = await fetch('py/'+name);
      if (!response.ok) throw Error('Missing module: '+name);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)), b=>b.toString(16).padStart(2,'0')).join('');
      if (hash !== expected) throw Error('Module checksum mismatch: '+name);
      py.FS.writeFile('/ace/'+name, bytes);
    }));
    const failed = results.filter(x => x.status === 'rejected');
    if(failed.length) throw failed[0].reason;
    py.runPython("import sys; sys.path.insert(0, '/ace')\nfrom browser_bridge import run_browser_report");
    self.postMessage({type:'ready'});
  })();
  ready.catch(error => {console.error(error); self.postMessage({type:'fatal',text:'The local Python tools could not load. Reload the page. If this continues, ask the study team to check the app installation.'});});
  let sequence = Promise.resolve();
  self.onmessage = event => {
    sequence = sequence.then(async () => {
      const {id, csvText, dictionaryText, sourceName, builtAt} = event.data;
      try {
        await ready;
        self.postMessage({type:'status',id,text:'Checking the export and building your dashboard…'});
        const run = py.globals.get('run_browser_report');
        let result;
        try {
          result = JSON.parse(run(csvText, dictionaryText,
            py.FS.readFile('/ace/survey_queue_logic.csv',{encoding:'utf8'}),
            py.FS.readFile('/ace/form_display_logic.csv',{encoding:'utf8'}),sourceName,builtAt));
        } finally {run.destroy();}
        self.postMessage({type:'result',id,result});
      } catch(error) {
        console.error(error);
        self.postMessage({type:'failure',id,text:'The dashboard could not be built. Check that both files are original REDCap CSV downloads. Ask the study team for help if this continues.'});
      }
    });
  };
} else {
  const $ = id => document.getElementById(id);
  let reportFile = null, dictionaryFile = null, generation = 0, urls = [];
  let worker;
  function status(text, level='info', append=true) {
    if(!append) $('status').replaceChildren();
    const line = document.createElement('p'); line.textContent = text; line.className='status-'+level;
    $('status').appendChild(line); $('status').scrollTop=$('status').scrollHeight;
  }
  function clearOutput() {
    $('output').style.display='none'; $('dashboardFrame').removeAttribute('src');
    urls.forEach(URL.revokeObjectURL); urls=[]; window.aceReport=null;
  }
  function fail(text, area='dropArea') {
    $(area).classList.remove('uploaded'); $(area).classList.add('error');
    $(area==='dictArea'?'dictLabel':'fileLabel').textContent=text;
    status(text,'error'); $('progress').hidden=true; clearOutput();
  }
  const decode = async file => new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer());
  async function run() {
    const id=++generation;
    clearOutput();
    if(!reportFile) return;
    $('progress').hidden=false;
    $('dropArea').classList.remove('error','uploaded');
    $('fileLabel').textContent='Checking '+reportFile.name+'…';
    status('Reading your file locally…','info',false);
    const inputs=[decode(reportFile),dictionaryFile ? decode(dictionaryFile) : Promise.resolve(null)];
    const results=await Promise.allSettled(inputs);
    if(id!==generation) return;
    const failed=results.findIndex(result=>result.status==='rejected');
    if(failed!==-1) {
      console.error(results[failed].reason);
      fail('This file is not a readable UTF-8 CSV. Use the original REDCap download.',failed===1?'dictArea':'dropArea'); return;
    }
    if(!worker) {fail('Python could not start. Reload the page to try again.');return;}
    worker.postMessage({id,csvText:results[0].value,dictionaryText:results[1].value,sourceName:reportFile.name,builtAt:new Date().toISOString()});
  }
  function input(areaId,inputId,dict=false) {
    const area=$(areaId), control=$(inputId);
    const choose=file=>{
      if(!file) return;
      if(!/\.csv$/i.test(file.name)) {generation++; fail('Choose a CSV exported from REDCap.',areaId);return;}
      area.classList.remove('error','dragover');
      if(dict) {dictionaryFile=file;$('dictLabel').textContent=file.name;area.classList.add('uploaded');$('clearDict').hidden=false;}
      else {reportFile=file;}
      run();
    };
    area.addEventListener('click',()=>control.click());
    control.addEventListener('change',()=>{choose(control.files[0]); control.value='';});
    area.addEventListener('dragover',event=>{event.preventDefault();area.classList.add('dragover');});
    area.addEventListener('dragleave',()=>area.classList.remove('dragover'));
    area.addEventListener('drop',event=>{event.preventDefault();area.classList.remove('dragover');choose(event.dataTransfer.files[0]);});
  }
  input('dropArea','fileInput'); input('dictArea','dictInput',true);
  document.addEventListener('dragover',e=>e.preventDefault());
  document.addEventListener('drop',e=>e.preventDefault());
  $('clearDict').onclick=()=>{dictionaryFile=null;$('dictLabel').textContent='Optional: add the data dictionary CSV';$('dictArea').classList.remove('uploaded','error');$('clearDict').hidden=true;run();};
  $('print').onclick=()=>{$('dashboardFrame').contentWindow.focus();$('dashboardFrame').contentWindow.print();};
  function show(result) {
    clearOutput();
    if(!result.ok) {
      const errors=result.findings.filter(f=>f.level==='error');
      fail(errors.map(f=>f.text).join(' '));return;
    }
    window.aceReport=result;
    $('warnings').replaceChildren();
    result.findings.filter(f=>f.level==='warning').forEach(f=>{const p=document.createElement('p');p.textContent=f.text;$('warnings').appendChild(p);});
    const links={dashboard:'downloadDashboard',numeric:'downloadNumeric',audit:'downloadAudit',table1:'downloadTable1'};
    for(const [key,file] of Object.entries(result.files)) {
      const bytes=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:file.type+';charset=utf-8'}));urls.push(url);
      const a=$(links[key]);a.href=url;a.download=file.name;
      if(key==='dashboard') {$('dashboardFrame').src=url;$('openDashboard').href=url;}
    }
    $('dropArea').classList.remove('error');$('dropArea').classList.add('uploaded');$('fileLabel').textContent=reportFile.name;
    $('summary').textContent=result.summary.records+' records · '+result.summary.included_n+' included';
    $('output').style.display='block';$('progress').hidden=true;
    $('status').replaceChildren();result.messages.forEach(m=>status(m.text,m.level));
  }
  try {
    worker=new Worker('app.js');
    worker.onmessage=event=>{
      const message=event.data;
      if(message.id!==undefined && message.id!==generation) return;
      if(message.type==='status') status(message.text);
      if(message.type==='ready' && !reportFile) {status('Ready. Add a report CSV to begin.');$('progress').hidden=true;}
      if(message.type==='result') show(message.result);
      if(message.type==='fatal'||message.type==='failure') fail(message.text);
    };
    worker.onerror=error=>{console.error(error);fail('Python could not start. Reload the page or ask the study team to check the app installation.');};
  } catch(error) {console.error(error);fail('This browser could not start the local tools. Try an up-to-date Chrome, Edge, Firefox, or Safari browser.');}
  fetch('version.json').then(r=>{if(!r.ok) throw Error('Missing version');return r.json();}).then(v=>{
    $('version').textContent='Build '+v.commit.replace(/^source-/,'').slice(0,12)+' · '+v.built_at+' · '+v.rule_version+' · Draft definitions';
  }).catch(error=>{console.error(error);$('version').textContent='Build information unavailable · Draft definitions';});
  window.addEventListener('beforeunload',()=>{urls.forEach(URL.revokeObjectURL);worker?.terminate();});
}
