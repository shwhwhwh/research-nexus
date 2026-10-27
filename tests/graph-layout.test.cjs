const {test}=require('node:test'),assert=require('node:assert/strict');
const {arrange,route,routes,bounds}=require('../web/graph-layout.js');
const nodes=[{id:'orx',builtin:'openresearch'},{id:'alpha',builtin:'alpha'},{id:'z',builtin:'zotero'},{id:'sample'},{id:'notes'}];
const edges=[{id:'one',source:'orx',target:'alpha'},{id:'two',source:'orx',target:'z'},{id:'three',source:'alpha',target:'z'},{id:'four',source:'sample',target:'notes'}];
for(const mode of ['orbital','structured'])test(mode+' template is deterministic, nonoverlapping and routes every edge',()=>{
  const ns=arrange(nodes,edges,mode);assert.deepEqual(ns,arrange(nodes,edges,mode));
  for(const a of ns)for(const b of ns)if(a!==b)assert(a.x+210<=b.x||b.x+210<=a.x||a.y+132<=b.y||b.y+132<=a.y,'overlapping cards');
  for(const e of edges){const r=route(ns,edges,e,mode);assert(!/NaN|undefined|Infinity/.test(r.d));assert(r.d.startsWith('M'));assert(Number.isFinite(r.x)&&Number.isFinite(r.y));}
  const b=bounds(ns,edges,mode);for(const n of ns)assert(n.x>=b.minX&&n.x+210<=b.maxX&&n.y>=b.minY&&n.y+132<=b.maxY);
  assert.deepEqual(nodes.map(n=>n.id),ns.map(n=>n.id));assert(!nodes.some(n=>'x'in n));
});
test('cycles and reverse/parallel connections have distinct bounded routes',()=>{
  const es=[...edges,{id:'reverse',source:'z',target:'alpha'},{id:'parallel',source:'orx',target:'z'}];
  for(const mode of ['orbital','structured']){
    const ns=arrange(nodes,es,mode),routes=es.map(e=>route(ns,es,e,mode));
    assert.equal(new Set(routes.map(r=>r.d)).size,es.length);assert(!routes.some(r=>/NaN|Infinity/.test(r.d)));
  }
});
test('sixty tools remain nonoverlapping and disconnected components are preserved',()=>{
  const many=Array.from({length:60},(_,i)=>({id:'tool-'+i}));
  for(const mode of ['orbital','structured']){const ns=arrange(many,[],mode);assert.equal(ns.length,60);for(const a of ns)for(const b of ns)if(a!==b)assert(a.x+210<=b.x||b.x+210<=a.x||a.y+132<=b.y||b.y+132<=a.y);}
});

test('template labels avoid tool cards and one another',()=>{for(const mode of ['orbital','structured']){const ns=arrange(nodes,edges,mode),rs=routes(ns,edges,mode);for(const r of rs){for(const n of ns)assert(r.x+r.width/2<=n.x||r.x-r.width/2>=n.x+210||r.y+14<=n.y||r.y-14>=n.y+132);for(const other of rs)if(other!==r)assert(Math.abs(r.x-other.x)>=(r.width+other.width)/2||Math.abs(r.y-other.y)>=28);}}});
