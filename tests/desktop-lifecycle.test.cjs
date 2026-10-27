const {test}=require('node:test');
const assert=require('node:assert/strict');
const createQuitGuard=require('../desktop/quit-guard.cjs');
const NativeApps=require('../desktop/native-apps.cjs');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

test('repeated quit stays blocked until native cleanup finishes',async()=>{
  const gate=deferred();let attempts=0,quits=0,blocked=0;
  const guard=createQuitGuard({cleanup:()=>{attempts++;return gate.promise;},quit:()=>quits++});
  const event={preventDefault:()=>blocked++};
  const pending=guard.handle(event);guard.handle(event);
  await Promise.resolve();
  assert.equal(attempts,1);assert.equal(blocked,2);assert.equal(guard.busy,true);assert.equal(guard.allowed,false);
  gate.resolve();await pending;
  assert.equal(quits,1);assert.equal(guard.allowed,true);
  guard.handle(event);assert.equal(blocked,2);
});

test('failed detach keeps the owner alive and permits a safe retry',async()=>{
  let attempts=0,quits=0,errors=0;
  const guard=createQuitGuard({cleanup:async()=>{if(++attempts===1)throw Error('pipe lost');},quit:()=>quits++,onError:()=>errors++});
  const event={preventDefault(){}};
  await guard.handle(event);assert.equal(guard.allowed,false);assert.equal(guard.busy,false);assert.equal(quits,0);assert.equal(errors,1);
  await guard.handle(event);assert.equal(quits,1);
});

function nativeFixture(){
  const native=new NativeApps(__dirname,{});let ended=0;
  native.requiresDetach=true;native.socket={writable:true,end:()=>ended++};native.connect=async()=>{};
  return {native,ended:()=>ended};
}
test('native detach waits beyond the former one second exit deadline',async()=>{
  const {native,ended}=nativeFixture();const gate=deferred();let finished=false;
  native.request=()=>gate.promise;
  const pending=native.detach().then(()=>{finished=true;});
  await new Promise(resolve=>setTimeout(resolve,1100));
  assert.equal(finished,false);assert.equal(ended(),0);
  gate.resolve({ok:true,detached:true});await pending;
  assert.equal(native.requiresDetach,false);assert.equal(ended(),1);
});
test('missing or failed acknowledgement never authorizes native destruction',async()=>{
  for(const outcome of [{ok:true},null,new Error('timeout')]) {
    const {native,ended}=nativeFixture();
    native.request=async()=>{if(outcome instanceof Error)throw outcome;return outcome;};
    await assert.rejects(native.detach());assert.equal(native.requiresDetach,true);assert.equal(ended(),0);
  }
});
test('lost pipe reconnects before asking the host to verify detach',async()=>{
  const {native}=nativeFixture();native.socket=null;let reconnected=false;
  native.connect=async()=>{reconnected=true;native.socket={end(){}};};
  native.request=async()=>{assert.equal(reconnected,true);return {detached:true};};
  await native.detach();assert.equal(native.requiresDetach,false);
});
test('an unused native host needs no detach connection',async()=>{
  const native=new NativeApps(__dirname,{});native.connect=()=>{throw Error('must not connect');};
  await native.detach();
});
