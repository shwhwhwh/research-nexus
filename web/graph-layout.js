/* Presentation only: layout and routing never change integration contracts. */
(function(root,factory){const api=factory();if(typeof module==='object')module.exports=api;else root.NexusGraph=api;})(globalThis,()=>{
  const W=210,H=132,TAU=Math.PI*2;
  const order=nodes=>[...nodes].sort((a,b)=>({openresearch:0,alpha:1,zotero:2}[a.builtin]??3)-({openresearch:0,alpha:1,zotero:2}[b.builtin]??3)||a.id.localeCompare(b.id));
  function arrange(nodes,edges,mode){
    const sorted=order(nodes),positions={};
    if(mode==='orbital'){
      // Elliptical celestial chart, with circumference sized for readable cards.
      const rx=Math.max(330,sorted.length*53),ry=Math.max(238,sorted.length*37);
      sorted.forEach((n,i)=>{const a=-Math.PI/2+i*TAU/sorted.length;positions[n.id]={x:Math.round(420+rx*Math.cos(a)-W/2),y:Math.round(330+ry*Math.sin(a)-H/2)};});
    }else{
      // Weak components get separate rows; longest DAG ranks give left-to-right flow.
      const remaining=new Set(sorted.map(n=>n.id));let offset=80;
      while(remaining.size){
        const component=new Set(),queue=[remaining.values().next().value];
        while(queue.length){const id=queue.shift();if(component.has(id))continue;component.add(id);remaining.delete(id);for(const e of edges)if(e.source===id||e.target===id){const other=e.source===id?e.target:e.source;if(remaining.has(other))queue.push(other);}}
        const ns=sorted.filter(n=>component.has(n.id)),rank=new Map(),pending=new Set(component);
        while(pending.size){let ready=ns.filter(n=>pending.has(n.id)&&!edges.some(e=>e.target===n.id&&pending.has(e.source)));if(!ready.length)ready=[ns.find(n=>pending.has(n.id))];for(const n of ready){rank.set(n.id,Math.max(0,...edges.filter(e=>e.target===n.id&&rank.has(e.source)).map(e=>rank.get(e.source)+1)));pending.delete(n.id);}}
        const columns=new Map();for(const n of ns){const level=rank.get(n.id),row=columns.get(level)||0;positions[n.id]={x:70+level*350,y:offset+row*222};columns.set(level,row+1);}
        offset+=Math.max(...columns.values())*222+90;
      }
    }
    return nodes.map(n=>({...n,...positions[n.id]}));
  }
  const center=n=>({x:n.x+W/2,y:n.y+H/2});
  function boundary(n,t){const c=center(n),dx=t.x-c.x,dy=t.y-c.y,scale=1/Math.max(Math.abs(dx)/(W/2+3),Math.abs(dy)/(H/2+3),.001);return{x:c.x+dx*scale,y:c.y+dy*scale};}
  function route(nodes,edges,edge,mode){
    const a=nodes.find(n=>n.id===edge.source),b=nodes.find(n=>n.id===edge.target);if(!a||!b)return{d:'',x:0,y:0};
    const ac=center(a),bc=center(b),siblings=edges.filter(e=>[e.source,e.target].sort().join('|')===[edge.source,edge.target].sort().join('|')).sort((a,b)=>a.id.localeCompare(b.id)),lane=siblings.indexOf(edge)-(siblings.length-1)/2;
    if(mode==='structured'){
      const index=edges.findIndex(e=>e.id===edge.id),forward=b.x>a.x+W,clear=forward&&!nodes.some(n=>n!==a&&n!==b&&n.x>a.x&&n.x<b.x&&Math.abs(center(n).y-(ac.y+bc.y)/2)<H);
      if(clear){const x=(a.x+W+b.x)/2+lane*24;return{d:`M${a.x+W+3} ${ac.y} H${x} V${bc.y} H${b.x-3}`,x,y:(ac.y+bc.y)/2-17};}
      const y=Math.min(...nodes.map(n=>n.y))-48-index*32;
      return{d:`M${ac.x} ${a.y-3} V${y} H${bc.x} V${b.y-3}`,x:(ac.x+bc.x)/2,y:y-17};
    }
    const hub={x:(Math.min(...nodes.map(n=>n.x))+Math.max(...nodes.map(n=>n.x+W)))/2,y:(Math.min(...nodes.map(n=>n.y))+Math.max(...nodes.map(n=>n.y+H)))/2};
    const mx=(ac.x+bc.x)/2,my=(ac.y+bc.y)/2,dx=mx-hub.x,dy=my-hub.y,len=Math.hypot(dx,dy)||1;
    const bend=80+Math.abs(lane)*50,c={x:mx+dx/len*bend,y:my+dy/len*bend};
    if(len<40){c.x=mx+(bc.y-ac.y)*.3;c.y=my-(bc.x-ac.x)*.3;}
    c.x+=lane*28;c.y+=lane*32;
    const start=boundary(a,c),end=boundary(b,c);
    return{d:`M${start.x} ${start.y} Q${c.x} ${c.y} ${end.x} ${end.y}`,x:(start.x+2*c.x+end.x)/4,y:(start.y+2*c.y+end.y)/4-15};
  }
  function routes(nodes,edges,mode){
    const placed=[];
    return edges.map(edge=>{
      const r=route(nodes,edges,edge,mode),units=[...(edge.data_type||'说明数据用途')].reduce((sum,c)=>sum+(c.charCodeAt(0)>255?2:1),0),width=Math.min(164,Math.max(100,units*6.8+22));
      const offsets=[{dx:0,dy:0}];for(let d=28;d<=196;d+=28)for(const [dx,dy] of [[-d,0],[d,0],[0,-d],[0,d],[-d,-d],[d,-d],[-d,d],[d,d]])offsets.push({dx,dy});
      offsets.sort((a,b)=>a.dx*a.dx+a.dy*a.dy-b.dx*b.dx-b.dy*b.dy);
      const collides=(x,y)=>nodes.some(n=>x+width/2>n.x-9&&x-width/2<n.x+W+9&&y+14>n.y-9&&y-14<n.y+H+9)||placed.some(p=>Math.abs(x-p.x)<(width+p.width)/2+8&&Math.abs(y-p.y)<36);
      const offset=offsets.find(o=>!collides(r.x+o.dx,r.y+o.dy))||offsets[0];
      const result={...r,id:edge.id,width,x:r.x+offset.dx,y:r.y+offset.dy};placed.push(result);return result;
    });
  }
  function bounds(nodes,edges,mode){const points=routes(nodes,edges,mode);return{minX:Math.min(...nodes.map(n=>n.x),...points.map(p=>p.x-p.width/2)),maxX:Math.max(...nodes.map(n=>n.x+W),...points.map(p=>p.x+p.width/2)),minY:Math.min(...nodes.map(n=>n.y),...points.map(p=>p.y-16)),maxY:Math.max(...nodes.map(n=>n.y+H),...points.map(p=>p.y+16))};}
  return{arrange,route,routes,bounds};
});
