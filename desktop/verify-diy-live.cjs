// Explicit opt-in acceptance test in the real RN window. Requires a private,
// user-selected project in data/research-test-scope.json. Never records screens.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=async function verifyDiyLive({root,win,origin}) {
  const scope=JSON.parse(fs.readFileSync(path.join(root,'data','research-test-scope.json'),'utf8'));
  const progress=path.join(root,'data','diy-live-check-progress.json');
  const report={passed:false,projectSelectedByUser:true,maxPapers:2,stages:[],runs:[]};
  const mark=stage=>{report.stages.push(stage);fs.writeFileSync(progress,JSON.stringify(report,null,2));};
  const js=code=>win.webContents.executeJavaScript(code);
  async function api(route,body){return js(`api(${JSON.stringify(route)},${body===undefined?'undefined':JSON.stringify(body)})`);}
  const delay=ms=>new Promise(r=>setTimeout(r,ms));
  async function until(fn,timeout=30000){const deadline=Date.now()+timeout;do{const value=await fn();if(value)return value;await delay(250);}while(Date.now()<deadline);throw Error('DIY acceptance step timed out: '+report.stages.at(-1));}
  const click=selector=>js(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled)throw Error('UI action unavailable');e.click();})()`);
  async function action(edge,kind,button){
    await js(`document.querySelector('[data-edge="${edge}"]').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:1}))`);
    await until(()=>js(`!!document.querySelector('[data-d="${button}"]:not([disabled])')`));
    const before=new Set((await api('/api/designer')).runs.map(r=>r.id));
    await click(`[data-d="${button}"]`);
    return until(async()=>{
      const r=(await api('/api/designer')).runs.find(r=>r.edge_id===edge&&r.kind===kind&&!before.has(r.id));
      if(r?.status==='error')throw Error(r.error);
      return r&&!['running','generating','testing'].includes(r.status)?r:false;
    },480000);
  }
  try{
    await until(()=>js('!!document.querySelector("main h1")'));
    await click('[data-page="designer"]');
    await until(()=>js('!!document.querySelector("[data-edge=existing-archive]")'));
    mark('DIY canvas visible');
    await click('[data-d="research"]');
    await until(()=>js('document.querySelector("#research-setup-dialog").open'));
    await js(`(()=>{const f=document.querySelector('#research-setup-form');for(const o of f.querySelector('[name=projects]').options)o.selected=o.value===${JSON.stringify(scope.project_id)};f.elements.max_papers.value='2';f.elements.include_tools.checked=false;f.elements.classifier.value=${JSON.stringify(scope.classifier||'keywords')};f.elements.allow_model_context.checked=${scope.model_context_authorized===true};f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));})()`);
    await until(async()=>{
      const edge=(await api('/api/designer')).project.edges.find(e=>e.id==='orx-project-alpha');
      return edge?.research_scope?.classifier===(scope.classifier||'keywords')&&edge.research_scope.project_ids.length===1&&
        edge.research_scope.project_ids[0]===scope.project_id&&await js('!document.querySelector("#research-setup-dialog").open');
    });
    mark('Project wizard created two scoped draft edges');
    await until(()=>js('!!document.querySelector("[data-edge=orx-project-alpha]")'));
    const preview=await api('/api/designer/research-preview',{edge_id:'orx-project-alpha'});
    assert.equal(preview.papers,2);assert(preview.records.every(r=>r.project_id===scope.project_id));
    if(scope.classifier&&scope.classifier!=='keywords')assert(preview.records.every(r=>r.classifier===scope.classifier));
    mark('Read-only preview found two real project papers');
    const first={},repeat={};
    for(const edge of ['orx-project-alpha','orx-project-zotero']){
      mark('Generating '+edge+' with local Codex');
      const build=await action(edge,'build','build');assert.equal(build.status,'candidate');
      assert.equal(build.plan.readiness,'ready');
      await until(()=>js(`!!document.querySelector('#designer-version option[value="${build.id}"]')`));
      await js(`(()=>{const s=document.querySelector('#designer-version');s.value=${JSON.stringify(build.id)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      mark('Testing generated '+edge+' plan');
      const test=await action(edge,'test','test');assert.equal(test.status,'tested');assert.equal(test.result.dry_run,true);
      await until(()=>js('!!document.querySelector("[data-d=activate]:not([disabled])")'));
      await click('[data-d=activate]');
      await until(async()=>!!(await api('/api/designer')).project.active[edge]);
      mark('Running '+edge+' with real configured accounts');
      const run=await action(edge,'execute','run-edge');assert.equal(run.status,'success');
      first[edge]=run.result.data;report.runs.push({edge,build:build.id,first:run.id});
    }
    for(const edge of ['orx-project-alpha','orx-project-zotero']){
      mark('Repeating '+edge+' to verify deduplication');
      const run=await action(edge,'execute','run-edge');assert.equal(run.status,'success');
      repeat[edge]=run.result.data;
    }
    assert.equal(first['orx-project-alpha'].verified_memberships,4);
    assert.equal(repeat['orx-project-alpha'].created_folders,0);
    assert.equal(first['orx-project-zotero'].papers.length,2);
    assert.equal(repeat['orx-project-zotero'].created_papers,0);
    assert.equal(repeat['orx-project-zotero'].created_notes,0);
    assert.equal(repeat['orx-project-zotero'].existing_notes,2);
    assert.deepEqual(repeat['orx-project-zotero'].papers,first['orx-project-zotero'].papers);
    report.passed=true;report.papers=2;report.first=first;report.repeat=repeat;
    mark('Real project sync and repeated-run identity checks passed');
    fs.writeFileSync(path.join(root,'data','diy-live-check.json'),JSON.stringify(report,null,2));
    await click('[data-d=logs]');
  }catch(e){report.error=e.message;mark('Failed');throw e;}
  return report;
};
