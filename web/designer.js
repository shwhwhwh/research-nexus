/* Research Nexus visual controller. No generated code is evaluated in the UI. */
window.NexusDesigner = (() => {
  let instance;
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const uid = prefix => prefix+'-'+crypto.randomUUID().slice(0,8);
  const short=(value,budget)=>{let result='',width=0;for(const char of String(value)){width+=char.charCodeAt(0)>255?2:1;if(width>budget)return result+'…';result+=char;}return result;};
  const kindName = kind => ({website:'网页 / API',app:'本地应用',folder:'输出目录'}[kind]||kind);
  const statusName = value => ({generating:'Agent 生成中',candidate:'待测试',running:'运行中',tested:'样例测试通过',success:'运行完成',error:'需要修复',cancelled:'已停止',interrupted:'上次中断'}[value]||value);
  class Designer {
    constructor(root,services) {
      this.root=root;Object.assign(this,services);this.selection=null;this.dirty=false;this.provider='codex';this.camera={x:12,y:12,z:.9};this.connecting=null;this.logOpen=false;
      this.root.innerHTML=`<section class="nexus-designer"><header class="designer-header"><div><div class="designer-eyebrow">DESIGN YOUR RESEARCH SYSTEM</div><h1>把工具连接成你的科研系统。</h1><p>画出数据流向，说明用途，让本地 Agent 帮你实现。</p></div><div class="designer-header-actions"><button class="button" data-d="demo">示例流程</button><button class="button" data-d="add">＋ 添加工具</button><button class="button" data-d="save">保存画布</button><button class="button primary" data-d="run-graph">运行系统 ↗</button></div></header>
        <div class="designer-grid"><div class="designer-board"><div class="board-title"><span class="status-dot"></span><b>我的科研系统</b><span id="designer-save-state">正在载入…</span><button class="button small" data-d="connect-mode">连接工具</button></div><svg class="flow-canvas" aria-label="科研工具与数据流向画布" tabindex="0"><defs><pattern id="flow-dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" class="flow-dot"/></pattern><marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1 7 4 1 7"/></marker></defs><rect width="100%" height="100%" fill="url(#flow-dots)"/><g class="flow-world"></g></svg><div class="board-help">拖动工具卡片排布 · 从右侧圆点连到目标工具左侧 · 拖动空白处平移</div><div class="canvas-controls"><button data-d="zoom-out" title="缩小">−</button><span id="designer-zoom">90%</span><button data-d="zoom-in" title="放大">＋</button><button data-d="fit" title="适应画布">适应</button><button data-d="logs">活动与版本 <span id="designer-run-count">0</span></button></div></div>
        <aside class="designer-inspector" aria-label="工具与数据流设置"></aside><section class="designer-activity hidden"></section></div><dialog class="designer-dialog"><form id="designer-add-form"><div class="designer-dialog-head"><h2>添加科研工具</h2><button class="icon-button" type="button" data-d="close-dialog">✕</button></div><p>添加常用网页、API、本地应用或输出目录，然后在画布中连接它。</p><div class="field"><label>名称</label><input name="name" required maxlength="80" placeholder="例如：Semantic Scholar、Obsidian"></div><div class="field"><label>类型</label><select name="kind"><option value="website">网页 / API</option><option value="app">本地应用</option><option value="folder">本地输出目录</option></select></div><div class="field"><label>网页或 API 地址（可选）</label><input name="url" placeholder="https://…"></div><div class="field"><label>API 基础地址（可选）</label><input name="api_url" placeholder="网页与 API 地址不同时填写"></div><div class="field"><label>授权变量名（可选，不填密钥）</label><input name="credential_env" placeholder="例如 NEXUS_MYTOOL_KEY"></div><div class="field"><label>本地程序（应用类型必填）</label><div class="designer-inline"><input name="executable" readonly placeholder="选择已安装的 .exe 程序"><button type="button" class="button" data-d="pick-exe">选择</button></div></div><div class="field"><label>它提供什么数据或能力？</label><textarea name="description" rows="3" placeholder="供 Agent 理解这个工具的接口、数据格式和用途。"></textarea></div><button class="button primary" type="submit">添加到画布</button></form></dialog></section>`;
      this.board=root.querySelector('.flow-canvas');this.world=root.querySelector('.flow-world');this.inspector=root.querySelector('.designer-inspector');this.activity=root.querySelector('.designer-activity');
      this.click=event=>this.onClick(event);this.input=event=>this.onInput(event);this.submit=event=>this.onSubmit(event);
      this.root.querySelector('.designer-header-actions').insertAdjacentHTML('afterbegin','<button class="button primary" data-d="research">连接项目文献</button>');
      this.root.querySelector('.designer-header p').textContent='画线 → 本地 Agent 生成版本 → 预览 → 启用。只有启用的版本才会写入目标工具。';
      this.root.insertAdjacentHTML('beforeend',`<dialog id="research-setup-dialog" class="designer-dialog"><form id="research-setup-form"><div class="designer-dialog-head"><h2>OpenResearch 项目文献流</h2><button type="button" class="icon-button" data-d="close-research">✕</button></div><p>alphaXiv 保存项目收藏与分类；其官方接口尚不支持写入笔记或高亮，因此引用原文与出处保存到 Zotero。只读取已完成对话的当前分支。</p><div class="field"><label>选择项目（可多选）</label><select id="research-projects" name="projects" multiple size="5" required></select></div><div class="field"><label>每次最多处理论文数</label><input name="max_papers" type="number" min="1" max="200" value="25" required></div><div class="field"><label>分类规则（名称与关键词，可修改 JSON）</label><textarea name="categories" rows="6">[{"name":"模型与方法","keywords":["model","architecture","transformer","模型","方法"]},{"name":"训练与优化","keywords":["training","optimizer","scaling","训练","优化"]},{"name":"数据与评测","keywords":["dataset","benchmark","evaluation","数据","评测"]}]</textarea></div><div class="field"><label>研究内容分类</label><select name="classifier"><option value="keywords">关键词规则 · 不外发正文</option><option value="codex">Codex · 语义分类</option><option value="claude">Claude Code · 语义分类</option></select><small>语义分类会将所选项目的引用上下文交给已登录的模型服务，消耗其额度；重复结果缓存。</small></div><label class="research-option"><input type="checkbox" name="allow_model_context"> 我允许将本次所选项目的引用上下文发送给所选模型服务进行分类</label><label class="research-option"><input type="checkbox" name="include_user" checked> 包含用户在对话中引用的论文</label><label class="research-option"><input type="checkbox" name="include_tools"> 包含工具返回的论文链接（标记为检索发现）</label><label class="research-option"><input type="checkbox" name="download_pdf" checked> PDF 归档到已配置的同步目录</label><label class="research-option"><input type="checkbox" name="highlight_quotes" checked> 对已核实位置的逐字引文创建 Zotero 高亮</label><div class="field"><label>启用后检查频率</label><select name="schedule"><option value="manual">手动运行</option><option value="hourly">每小时</option><option value="daily">每天</option></select></div><p class="inspector-note">创建两条草稿连线；还需生成、测试并启用各自版本。不会修改已有收藏或人工笔记。</p><button class="button primary" type="submit">添加 / 更新两条项目连线</button></form></dialog>`);
      root.addEventListener('click',this.click);root.addEventListener('input',this.input);root.addEventListener('change',this.input);root.addEventListener('submit',this.submit);
      this.board.addEventListener('pointerdown',event=>this.pointerDown(event));this.board.addEventListener('pointermove',event=>this.pointerMove(event));this.board.addEventListener('pointerup',event=>this.pointerUp(event));this.board.addEventListener('pointercancel',()=>{this.drag=null;this.preview=null;this.paint();});
      this.board.addEventListener('wheel',event=>{if(event.ctrlKey||event.metaKey){event.preventDefault();this.zoom(event.deltaY<0?.1:-.1);}},{passive:false});
      this.poll();this.timer=setInterval(()=>this.poll(),2300);
    }
    destroy() {clearInterval(this.timer);clearTimeout(this.draftTimer);if(this.dirty)this.persistDraft();this.destroyed=true;this.root.removeEventListener('click',this.click);this.root.removeEventListener('input',this.input);this.root.removeEventListener('change',this.input);this.root.removeEventListener('submit',this.submit);}
    async poll() {
      if(this.polling||this.destroyed)return;this.polling=true;
      try {
        const data=await this.api('/api/designer');if(this.destroyed)return;
        const first=!this.project;this.remote=data;
        if(this.pendingVersion){
          const ready=data.versions?.find(v=>v.id===this.pendingVersion&&v.plan);
          if(ready){this.selectedVersion=ready.id;this.pendingVersion=null;}
          else if(data.runs.some(r=>r.id===this.pendingVersion&&['error','cancelled'].includes(r.status)))this.pendingVersion=null;
        }
        const graphStamp=JSON.stringify(data.project),graphChanged=graphStamp!==this.graphStamp;this.graphStamp=graphStamp;
        if(!this.dirty&&!this.drag)this.project=structuredClone(data.project);
        if(first){
          try{const draft=JSON.parse(localStorage.getItem('rn-designer-draft'));if(draft?.base_revision===data.project.revision&&draft.project.id===data.project.id){this.project={...data.project,name:draft.project.name,nodes:draft.project.nodes,edges:draft.project.edges};this.dirty=true;}}catch{}
          this.selection={type:'edge',id:'existing-archive'};this.paint();this.inspect();
        }
        const focused=this.inspector.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select');
        const inspectorStamp=JSON.stringify({selection:this.selection,active:data.project.active,versions:(data.versions||[]).map(v=>[v.id,v.tested,v.status]),runs:data.runs.map(r=>[r.id,r.status])});
        if(!focused&&!this.dirty&&inspectorStamp!==this.inspectorStamp){if(!first)this.inspect();this.inspectorStamp=inspectorStamp;}
        if(graphChanged&&!this.dirty&&!this.drag)this.paint();
        const activityStamp=JSON.stringify(data.runs);
        if(activityStamp!==this.activityStamp){this.activityStamp=activityStamp;this.renderActivity();}
        this.updateStatus();
      }catch(error){if(!this.remote)this.inspector.innerHTML=`<div class="designer-empty"><h2>暂时无法读取设计器</h2><p>${esc(error.message)}</p><button class="button" data-d="retry">重试</button></div>`;}
      finally{this.polling=false;}
    }
    updateStatus(){this.root.querySelector('#designer-save-state').textContent=this.dirty?'有未保存更改':'已保存到本机';this.root.querySelector('#designer-zoom').textContent=Math.round(this.camera.z*100)+'%';this.root.querySelector('#designer-run-count').textContent=this.remote?.runs.length||0;}
    persistDraft(){try{localStorage.setItem('rn-designer-draft',JSON.stringify({base_revision:this.project.revision,project:this.project}));}catch{}}
    markDirty(){this.dirty=true;this.updateStatus();clearTimeout(this.draftTimer);this.draftTimer=setTimeout(()=>this.persistDraft(),180);}
    async save(){const sample=this.inspector.querySelector('[data-edge-field=sample]');if(sample&&!sample.checkValidity())throw Error('测试样例不是有效 JSON，请先修正。');const data=await this.api('/api/designer/save',this.project);this.remote=data;this.project=structuredClone(data.project);this.dirty=false;clearTimeout(this.draftTimer);localStorage.removeItem('rn-designer-draft');this.updateStatus();this.paint();return data;}
    node(id){return this.project?.nodes.find(node=>node.id===id);}
    edge(id){return this.project?.edges.find(edge=>edge.id===id);}
    versions(id){return(this.remote?.versions||this.remote?.runs||[]).filter(run=>run.kind==='build'&&run.edge_id===id&&run.plan&&run.current_contract!==false);}
    path(edge){const a=this.node(edge.source),b=this.node(edge.target);if(!a||!b)return'';const x=a.x+210,y=a.y+66,tx=b.x,ty=b.y+66,d=Math.max(65,Math.abs(tx-x)*.5);return`M${x} ${y} C${x+d} ${y},${tx-d} ${ty},${tx} ${ty}`;}
    paint(){
      if(!this.project)return;
      this.world.setAttribute('transform',`translate(${this.camera.x} ${this.camera.y}) scale(${this.camera.z})`);
      let html=this.project.edges.map(edge=>{
        const active=edge.builtin||this.project.active[edge.id];const selected=this.selection?.id===edge.id;
        const a=this.node(edge.source),b=this.node(edge.target);if(!a||!b)return'';
        const label=edge.data_type||'说明数据用途';const x=(a.x+210+b.x)/2,y=(a.y+b.y)/2+42;
        return`<g class="flow-edge ${selected?'selected':''} ${active?'enabled':''}" data-edge="${esc(edge.id)}" role="button" tabindex="0" aria-label="${esc(a.name+' 到 '+b.name)}"><title>${esc(edge.purpose||label)}</title><path class="flow-edge-hit" d="${this.path(edge)}"/><path class="flow-edge-line" d="${this.path(edge)}" marker-end="url(#flow-arrow)"/><rect class="flow-edge-label" x="${x-50}" y="${y-13}" width="100" height="26" rx="13"/><text x="${x}" y="${y+5}" text-anchor="middle">${esc(short(label,13))}</text></g>`;
      }).join('');
      html+=this.project.nodes.map(node=>{
        const symbol=node.builtin==='alpha'?'α':node.builtin==='zotero'?'Z':node.builtin==='openresearch'?'◩':node.kind==='website'?'↗':node.kind==='folder'?'▤':'◇';
        const selected=this.selection?.type==='node'&&this.selection.id===node.id;
        return`<g class="flow-node ${selected?'selected':''} ${this.connecting===node.id?'connecting':''}" transform="translate(${node.x} ${node.y})" data-node="${esc(node.id)}" role="button" tabindex="0" aria-label="${esc(node.name)}"><rect class="flow-node-body" width="210" height="132" rx="14"/><rect class="flow-node-symbol-bg" x="16" y="17" width="34" height="34" rx="9"/><text class="flow-node-symbol ${node.builtin||''}" x="33" y="42" text-anchor="middle">${symbol}</text><text class="flow-node-title" x="61" y="33">${esc(short(node.name,19))}</text><text class="flow-node-kind" x="61" y="51">${esc(kindName(node.kind))}</text><text class="flow-node-description" x="17" y="79">${esc(short(node.description||'点击设置工具能力与用途',27))}</text><line x1="16" y1="96" x2="194" y2="96"/><text class="flow-node-status" x="17" y="116">${node.builtin?'● 已连接 · 内置集成':'○ 自定义工具'}</text><circle class="flow-port input" cx="0" cy="66" r="7" data-port-in="${esc(node.id)}"/><circle class="flow-port output" cx="210" cy="66" r="7" data-port-out="${esc(node.id)}"/></g>`;
      }).join('');
      if(this.preview)html+=`<path class="flow-edge-preview" d="${this.preview}"/>`;
      this.world.innerHTML=html;
    }
    select(type,id){this.selection={type,id};this.paint();this.inspect();}
    inspect(){
      if(!this.project)return;
      const selection=this.selection;
      if(!selection){this.inspector.innerHTML=`<div class="designer-empty"><span class="designer-inspector-kicker">TOP LEVEL CONTROLLER</span><h2>先画出你的研究方式。</h2><p>添加工具，从输出圆点连到输入圆点。选中连线，用一句话说明数据如何流动。</p><button class="button" data-d="add">＋ 添加第一个工具</button><p>画布和方案保存在本机。调用 Agent 会使用所选本地账号的额度。</p></div>`;return;}
      if(selection.type==='node'){
        const node=this.node(selection.id);if(!node){this.selection=null;return this.inspect();}
        this.inspector.innerHTML=`<div class="inspector-head"><span>工具设置</span><button class="icon-button" data-d="deselect">✕</button></div><div class="inspector-body"><h2>${esc(node.name)}</h2><span class="status-tag">${esc(kindName(node.kind))}</span><div class="field"><label>名称</label><input data-node-field="name" value="${esc(node.name)}" maxlength="80"></div><div class="field"><label>网页 / API 地址</label><input data-node-field="url" value="${esc(node.url||'')}" placeholder="https://…"></div><div class="field"><label>API 基础地址（可选）</label><input data-node-field="api_url" value="${esc(node.api_url||'')}" placeholder="https://api.…"></div><div class="field"><label>授权变量名（不填密钥）</label><input data-node-field="credential_env" value="${esc(node.credential_env||'')}" placeholder="NEXUS_MYTOOL_KEY"><small class="inspector-note">只有登记给这个工具的变量能用于它的请求。</small></div><div class="field"><label>能力与接口说明</label><textarea data-node-field="description" rows="5">${esc(node.description||'')}</textarea></div>${node.kind==='app'&&!node.builtin?`<div class="field"><label>本地程序</label><small>${esc(node.executable||'未选择')}</small><button class="button" data-d="change-exe">选择应用</button></div>`:''}<div class="inspector-actions"><button class="button primary" data-d="open-node">打开工具 ↗</button><button class="button" data-d="connect-from">从这里连线</button></div><hr><button class="button danger" data-d="delete" ${node.builtin?'disabled title="内置工具由现有设置管理"':''}>移除工具</button><p class="inspector-note">${node.kind==='website'?'网页会在 RN 内容区打开，并保留独立登录会话。':node.kind==='app'?'内置工具嵌入 RN；自定义应用以其原生窗口启动。':'输出保存在 RN 管理的本地目录，可随时打开。'}</p></div>`;
        return;
      }
      const edge=this.edge(selection.id);if(!edge){this.selection=null;return this.inspect();}
      const versions=this.versions(edge.id),active=this.project.active[edge.id],candidate=versions[0];
      const activeVersion=versions.find(v=>v.id===active?.version);
      this.selectedVersion=this.selectedVersion&&versions.some(v=>v.id===this.selectedVersion)?this.selectedVersion:(candidate?.id||'');
      const current=versions.find(v=>v.id===this.selectedVersion);
      const busy=(this.remote?.runs||[]).some(r=>r.edge_id===edge.id&&['generating','running','testing'].includes(r.status));
      this.inspector.innerHTML=`<div class="inspector-head"><span>数据流设置</span><button class="icon-button" data-d="deselect">✕</button></div><div class="inspector-body"><div class="flow-direction"><span>${esc(this.node(edge.source)?.name)}</span><b>→</b><span>${esc(this.node(edge.target)?.name)}</span></div><span class="status-tag ${edge.builtin||active?'good':''}">${edge.builtin?'原归档引擎 · 每天':active?'已启用版本 '+active.version.slice(0,6):'草稿 · 尚未启用'}</span>
        <div class="field"><label>这条连线要完成什么？</label><textarea data-edge-field="purpose" rows="4" placeholder="例如：读取新论文，按 DOI 去重，整理成 Markdown 阅读清单。">${esc(edge.purpose||'')}</textarea></div><div class="field"><label>流动的数据</label><input data-edge-field="data_type" value="${esc(edge.data_type||'')}" placeholder="论文 / PDF / 笔记 / 实验结果"></div><div class="field"><label>运行方式</label><select data-edge-field="schedule" ${edge.builtin?'disabled':''}>${[['manual','手动运行'],['hourly','每小时'],['daily','每天']].map(([v,t])=>`<option value="${v}" ${edge.schedule===v?'selected':''}>${t}</option>`).join('')}</select></div><details class="flow-sample"><summary>测试样例 · JSON</summary><textarea data-edge-field="sample" rows="6">${esc(JSON.stringify(edge.sample||[],null,2))}</textarea><small>样例测试模拟网络数据，不发送请求、不写入外部工具。</small></details>
        ${edge.builtin?`<div class="note">这条连线复用已经运行的去重归档流程。账户、同步频率和开关继续在“连接与设置”管理。</div><button class="button primary full" data-d="run-edge" ${busy?'disabled':''}>立即检查并归档</button>`:
        `<div class="inspector-section-title">让本地 Agent 实现</div><div class="field"><label>使用哪个 Agent？</label><select id="designer-provider">${(this.remote?.agents||[]).map(agent=>`<option value="${agent.id}" ${agent.id===this.provider?'selected':''} ${!agent.installed?'disabled':''}>${agent.name}${agent.installed?' · 已安装':' · 未找到'}</option>`).join('')}</select></div><button class="button primary full" data-d="build" ${busy?'disabled':''}>${busy?'Agent / 任务进行中…':'✦ 生成集成方案'}</button><small class="inspector-note">使用本地 CLI 的已有登录和默认模型，会消耗对应账号额度。</small>
        ${versions.length?`<div class="inspector-section-title">集成版本</div><select id="designer-version">${versions.map(v=>`<option value="${v.id}" ${current?.id===v.id?'selected':''}>${v.id.slice(0,6)} · ${v.tested?'已测试':'待测试'}${active?.version===v.id?' · 当前启用':''}</option>`).join('')}</select><p class="plan-summary">${esc(current?.plan.summary||'')}</p><p class="inspector-note">${esc((current?.plan.requirements||[]).join('；'))}</p><ol class="plan-steps">${current?.plan.steps.map(s=>`<li>${esc(({input:'接收输入',http_get:'读取接口',http_post:'发送到目标工具',select:'选择数据',map:'整理字段',filter:'筛选',dedupe:'去重',write_json:'保存 JSON',write_markdown:'保存 Markdown',builtin_archive:'调用现有归档',orx_citations:'读取项目引用与分类',alpha_project_library:'保存 alphaXiv 项目收藏',zotero_project_notes:'保存 Zotero 引用笔记与标记'})[s.op]||s.op)}</li>`).join('')}</ol>${current?.plan.notes?`<p class="inspector-note">${esc(current.plan.notes)}</p>`:''}<details><summary>查看方案详情</summary><pre class="plan-code">${esc(JSON.stringify(current?.plan,null,2))}</pre></details><div class="inspector-actions"><button class="button" data-d="test" ${busy?'disabled':''}>测试与预览</button><button class="button primary" data-d="activate" ${!current?.tested||current?.plan.readiness==='needs_setup'||busy?'disabled':''}>${active&&active.version!==current?.id?'切换 / 回退到此版本':'启用此版本'}</button></div>${active?`<div class="inspector-actions"><button class="button" data-d="run-edge" ${busy?'disabled':''}>运行连线</button><button class="button" data-d="disable">暂停</button></div>`:''}<div class="field"><label>希望 Agent 怎样改进？</label><textarea id="designer-feedback" rows="3" placeholder="例如：输出缺少 arXiv ID，请保留标题和编号。"></textarea></div><button class="button full" data-d="repair" ${busy?'disabled':''}>将失败记录交给 Agent 修订</button>`:`<div class="designer-gentle-empty">生成后，可以查看步骤、测试数据结果，再决定何时启用。</div>`}`}
        <hr><button class="button danger" data-d="delete" ${edge.builtin?'disabled':''}>删除连线</button></div>`;
      if(edge.research_scope){
        const preview=this.previews?.[edge.id];
        this.inspector.querySelector('.inspector-body').insertAdjacentHTML('afterbegin',`<div class="research-scope"><b>项目引用同步</b><p class="inspector-note">alphaXiv：项目收藏与分类。Zotero：引用上下文笔记；高亮需逐字定位。变更项目范围或规则后须重新生成并启用版本。</p><details><summary>项目范围与分类规则 · JSON</summary><textarea data-edge-field="research_scope" rows="10">${esc(JSON.stringify(edge.research_scope,null,2))}</textarea></details><button class="button full" data-d="source-preview">只读预览真实项目</button>${preview?`<p>${preview.papers} 篇论文 · ${preview.citations} 处引用 · 还有 ${preview.remaining_papers} 篇未纳入本次数量上限</p><details><summary>查看引用与归类</summary><pre class="plan-code">${esc(JSON.stringify(preview,null,2))}</pre></details>`:''}</div>`);
      }
    }
    onInput(event){
      if(!this.project)return;const target=event.target;
      if(target.id==='designer-provider'){this.provider=target.value;return;}
      if(target.id==='designer-version'){this.selectedVersion=target.value;this.inspect();return;}
      const nodeField=target.dataset.nodeField,edgeField=target.dataset.edgeField;
      if(nodeField&&this.selection?.type==='node'){this.node(this.selection.id)[nodeField]=target.value;this.markDirty();this.paint();}
      if(edgeField&&this.selection?.type==='edge'){
        let value=target.value;if(['sample','research_scope'].includes(edgeField)){try{value=JSON.parse(value);target.setCustomValidity('');}catch{target.setCustomValidity('请输入有效 JSON');return;}}
        this.edge(this.selection.id)[edgeField]=value;this.markDirty();if(edgeField==='data_type')this.paint();
      }
    }
    async onClick(event){
      const button=event.target.closest('[data-d]');if(!button)return;
      const action=button.dataset.d;
      try{
        if(action==='add')this.root.querySelector('dialog').showModal();
        else if(action==='research'){
          if(this.dirty)await this.save();
          const data=await this.api('/api/designer/research-projects');
          this.root.querySelector('#research-projects').innerHTML=data.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
          this.root.querySelector('#research-setup-dialog').showModal();
        }
        else if(action==='close-research')this.root.querySelector('#research-setup-dialog').close();
        else if(action==='source-preview'){
          if(this.dirty)await this.save();
          this.toast('正在只读检查实际对话，不写入外部工具…');
          const data=await this.api('/api/designer/research-preview',{edge_id:this.selection.id});
          this.previews??={};this.previews[this.selection.id]=data;this.inspect();
          this.toast(`预览：${data.papers} 篇论文，${data.citations} 处引用；尚未归档。`);
        }
        else if(action==='close-dialog')this.root.querySelector('dialog').close();
        else if(action==='retry')await this.poll();
        else if(action==='save'){await this.save();this.toast('画布已保存到本机。');}
        else if(action==='deselect'){this.selection=null;this.inspect();this.paint();}
        else if(action==='zoom-in')this.zoom(.1);else if(action==='zoom-out')this.zoom(-.1);else if(action==='fit')this.fit();
        else if(action==='connect-mode'){this.connecting=this.selection?.type==='node'?this.selection.id:null;this.toast('先点击源工具右侧圆点，再点击目标工具左侧圆点；也可以直接拖线。');this.paint();}
        else if(action==='connect-from'){this.connecting=this.selection.id;this.toast('点击目标工具左侧圆点完成连接。');this.paint();}
        else if(action==='logs'){this.logOpen=!this.logOpen;this.renderActivity();}
        else if(action==='pick-exe'||action==='change-exe'){
          if(!window.workspace?.chooseToolExecutable)throw Error('请通过桌面版选择本地应用。');
          const file=await window.workspace.chooseToolExecutable();if(file){if(action==='pick-exe')this.root.querySelector('[name=executable]').value=file;else{this.node(this.selection.id).executable=file;this.markDirty();this.inspect();}}
        }
        else if(action==='open-node'){
          const node=this.node(this.selection.id);if(this.dirty)await this.save();
          if(node.builtin)return this.openBuiltin(node.builtin);
          if(!window.workspace?.openDesignerNode)throw Error('请在 RN 桌面版打开工具。');
          const result=await window.workspace.openDesignerNode(node.id);
          if(result.tool)window.dispatchEvent(new CustomEvent('nexus-custom-tool',{detail:result}));else this.toast('已打开 '+node.name);
        }
        else if(action==='delete'){
          const s=this.selection;if(s.type==='node'){this.project.nodes=this.project.nodes.filter(n=>n.id!==s.id);this.project.edges=this.project.edges.filter(e=>e.source!==s.id&&e.target!==s.id);}else this.project.edges=this.project.edges.filter(e=>e.id!==s.id);
          this.selection=null;this.markDirty();this.paint();this.inspect();
        }
        else if(action==='demo')this.addDemo();
        else if(action==='select-run'){this.focusRun=button.dataset.run;this.logOpen=true;this.renderActivity();}
        else if(action==='cancel'){await this.api('/api/designer/cancel',{run_id:button.dataset.run});await this.poll();}
        else if(['build','repair','test','activate','disable','run-edge','run-graph'].includes(action)){
          if(this.dirty)await this.save();
          const edge=this.selection?.type==='edge'?this.edge(this.selection.id):null;
          const routes={build:'build',repair:'build',test:'test',activate:'activate',disable:'disable','run-edge':'run','run-graph':'run-graph'};
          const payload={edge_id:edge?.id,provider:this.provider,repair:action==='repair',version:this.selectedVersion,feedback:this.inspector.querySelector('#designer-feedback')?.value||''};
          const response=await this.api('/api/designer/'+routes[action],payload);this.focusRun=response.run_id;this.logOpen=true;
          if(['build','repair'].includes(action))this.pendingVersion=response.run_id;
          if(action==='activate')this.toast('此版本已启用。可手动运行，或按所选频率执行。');
          await this.poll();this.inspect();this.renderActivity();
        }
      }catch(error){this.toast(error.message,true);}
    }
    async onSubmit(event){
      if(event.target.id==='research-setup-form'){
        event.preventDefault();
        try{
          const form=new FormData(event.target),options={project_ids:form.getAll('projects'),max_papers:Number(form.get('max_papers')),categories:JSON.parse(form.get('categories')),classifier:form.get('classifier'),include_user:form.has('include_user'),include_tools:form.has('include_tools'),download_pdf:form.has('download_pdf'),highlight_quotes:form.has('highlight_quotes')};
          await this.api('/api/designer/research-setup',{research_scope:options,schedule:form.get('schedule'),allow_model_context:form.has('allow_model_context')});
          this.dirty=false;this.root.querySelector('#research-setup-dialog').close();await this.poll();this.select('edge','orx-project-alpha');this.fit();
          this.toast('两条项目连线已就绪。先预览真实引用，再分别生成、测试并启用。');
        }catch(error){this.toast(error.message,true);}
        return;
      }
      if(event.target.id!=='designer-add-form')return;event.preventDefault();
      try{
        const data=Object.fromEntries(new FormData(event.target));
        if(data.kind==='website'&&!data.url)throw Error('网页 / API 工具需要填写地址。');
        if(data.kind==='app'&&!data.executable)throw Error('请选择本地应用的 .exe 程序。');
        const id=uid('tool');this.project.nodes.push({...data,id,x:120+this.project.nodes.length%3*240,y:110+Math.floor(this.project.nodes.length/3)*190});
        this.root.querySelector('dialog').close();event.target.reset();this.markDirty();this.select('node',id);
      }catch(error){this.toast(error.message,true);}
    }
    addDemo(){
      const source=uid('papers'),target=uid('notes'),id=uid('flow');
      this.project.nodes.push({id:source,name:'样例论文',kind:'folder',description:'用样例 JSON 练习科研数据流',x:75,y:550},{id:target,name:'阅读清单',kind:'folder',description:'将处理结果保存为本地 Markdown',x:410,y:550});
      this.project.edges.push({id,source,target,purpose:'按 arxiv 字段去重，将 title 与 arxiv 整理为 Markdown 阅读清单，保存为 reading-list.md。输入为给定样例，不需要网络。',data_type:'论文列表 → Markdown',schedule:'manual',sample:[{title:'Spiking neural networks',arxiv:'2401.00001'},{title:'Embodied intelligence',arxiv:'2402.00002'},{title:'Spiking neural networks',arxiv:'2401.00001'}]});
      this.markDirty();this.select('edge',id);this.fit();this.toast('已加入无网络写入的示例。点击“生成集成方案”体验完整流程。');
    }
    point(event){const rect=this.board.getBoundingClientRect();return{x:(event.clientX-rect.left-this.camera.x)/this.camera.z,y:(event.clientY-rect.top-this.camera.y)/this.camera.z};}
    pointerDown(event){
      if(!this.project||event.button!==0)return;
      const out=event.target.closest('[data-port-out]'),input=event.target.closest('[data-port-in]'),node=event.target.closest('[data-node]'),edge=event.target.closest('[data-edge]');
      if(input&&this.connecting){this.addEdge(this.connecting,input.dataset.portIn);return;}
      if(out){this.connecting=out.dataset.portOut;this.drag={type:'line',source:this.connecting};this.board.setPointerCapture(event.pointerId);this.paint();return;}
      if(node){this.select('node',node.dataset.node);const p=this.point(event),n=this.node(node.dataset.node);this.drag={type:'node',id:n.id,dx:p.x-n.x,dy:p.y-n.y};}
      else if(edge){this.select('edge',edge.dataset.edge);return;}
      else this.drag={type:'pan',x:event.clientX,y:event.clientY,cx:this.camera.x,cy:this.camera.y};
      this.board.setPointerCapture(event.pointerId);
    }
    pointerMove(event){
      if(!this.drag)return;const point=this.point(event);
      if(this.drag.type==='node'){const node=this.node(this.drag.id);node.x=Math.round(point.x-this.drag.dx);node.y=Math.round(point.y-this.drag.dy);this.markDirty();}
      else if(this.drag.type==='pan'){this.camera.x=this.drag.cx+event.clientX-this.drag.x;this.camera.y=this.drag.cy+event.clientY-this.drag.y;}
      else{const node=this.node(this.drag.source),x=node.x+210,y=node.y+66;this.preview=`M${x} ${y} C${x+75} ${y},${point.x-75} ${point.y},${point.x} ${point.y}`;}
      this.paint();
    }
    pointerUp(event){
      if(this.drag?.type==='line'){
        const point=this.point(event),target=this.project.nodes.find(n=>Math.abs(n.x-point.x)<30&&Math.abs(n.y+66-point.y)<35);
        if(target)this.addEdge(this.drag.source,target.id);
      }
      this.drag=null;this.preview=null;this.paint();
    }
    addEdge(source,target){
      if(source===target)return;const existing=this.project.edges.find(e=>e.source===source&&e.target===target);
      if(existing){this.connecting=null;this.select('edge',existing.id);return;}
      const id=uid('flow');this.project.edges.push({id,source,target,purpose:'',data_type:'数据流',schedule:'manual',sample:[]});this.connecting=null;this.markDirty();this.select('edge',id);
    }
    zoom(amount){this.camera.z=Math.max(.35,Math.min(1.8,this.camera.z+amount));this.paint();this.updateStatus();}
    fit(){if(!this.project?.nodes.length)return;const nodes=this.project.nodes,minX=Math.min(...nodes.map(n=>n.x)),minY=Math.min(...nodes.map(n=>n.y)),maxX=Math.max(...nodes.map(n=>n.x+210)),maxY=Math.max(...nodes.map(n=>n.y+132));this.camera.z=Math.max(.35,Math.min(1,(this.board.clientWidth-80)/(maxX-minX),(this.board.clientHeight-110)/(maxY-minY)));this.camera.x=40-minX*this.camera.z;this.camera.y=50-minY*this.camera.z;this.paint();this.updateStatus();}
    renderActivity(){
      this.activity.classList.toggle('hidden',!this.logOpen);this.root.querySelector('.designer-grid').classList.toggle('with-activity',this.logOpen);if(!this.logOpen)return;
      const runs=this.remote?.runs||[],focus=runs.find(r=>r.id===this.focusRun)||runs[0];
      this.activity.innerHTML=`<div class="activity-list"><div class="activity-title">活动与版本</div>${runs.length?runs.slice(0,15).map(run=>`<button class="activity-run ${run.id===focus?.id?'active':''}" data-d="select-run" data-run="${run.id}"><span class="activity-status ${run.status}"></span><span><b>${esc(statusName(run.status))}</b><small>${esc((this.edge(run.edge_id)?.data_type||'整个系统')+' · '+new Date(run.time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))}</small></span></button>`).join(''):'<p class="inspector-note">还没有任务。先选择一条连线，再调用 Agent。</p>'}</div><div class="activity-detail">${focus?`<div class="activity-detail-head"><b>${esc(statusName(focus.status))}</b><span>${esc(focus.id.slice(0,8))}</span>${['generating','running','testing'].includes(focus.status)?`<button class="button small" data-d="cancel" data-run="${focus.id}">停止任务</button>`:''}</div>${focus.error?`<div class="designer-run-error">${esc(focus.error)}</div>`:''}${focus.logs.map(log=>`<p class="activity-log">${esc(log.text)}</p>`).join('')}${focus.result?`<details open><summary>${focus.result.dry_run?'样例结果预览 · 无真实读写':'运行结果'}</summary><pre>${esc(JSON.stringify(focus.result,null,2))}</pre></details>`:''}${focus.plan&&!focus.result?`<p class="plan-summary">${esc(focus.plan.summary)}</p>`:''}`:'<p class="inspector-note">生成、测试、启用和运行的记录会显示在这里。</p>'}</div>`;
    }
  }
  return {mount(root,services){if(instance?.root===root&&root.querySelector('.nexus-designer'))return;instance?.destroy();instance=new Designer(root,services);},unmount(){instance?.destroy();instance=null;}};
})();
