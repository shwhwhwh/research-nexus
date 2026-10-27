const { EventEmitter } = require('node:events');
const { spawn } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

module.exports = class NativeApps extends EventEmitter {
  constructor(root, window) {
    super(); this.root=root; this.window=window; this.sequence=0; this.pending=new Map();
    this.executable=path.join(root,'desktop','NativeDockHost.exe');
    this.requiresDetach=false;
    this.pipe='\\\\.\\pipe\\ResearchBridge.NativeDock.'+createHash('sha256').update(root.toLowerCase()).digest('hex').slice(0,16);
  }
  async connect() {
    if(this.socket?.writable)return;
    if(this.connecting)return this.connecting;
    this.connecting=(async()=>{
      if(!fs.existsSync(this.executable))throw new Error('本地窗口组件尚未编译，请运行 desktop/build-native-host.ps1。');
      let started=false;
      for(let n=0;n<60;n++) {
        const socket=await new Promise(resolve=>{
          const s=net.createConnection(this.pipe,()=>{s.removeAllListeners('error');resolve(s);});
          s.once('error',()=>{s.destroy();resolve(null);});
        });
        if(socket) {
          this.socket=socket;socket.setEncoding('utf8');let buffer='';
          socket.on('error',()=>{});
          socket.on('data',chunk=>{
            buffer+=chunk;let end;
            while((end=buffer.indexOf('\n'))>=0) {
              const line=buffer.slice(0,end);buffer=buffer.slice(end+1);
              try {
                const data=JSON.parse(line);
                if(data.event)this.emit('state',data);
                else if(this.pending.has(data.id)) {
                  const job=this.pending.get(data.id);this.pending.delete(data.id);clearTimeout(job.timer);
                  if(data.error)job.reject(new Error(data.error));else job.resolve(data.result);
                }
              } catch {}
            }
          });
          socket.on('close',()=>{
            if(this.socket===socket)this.socket=null;
            for(const job of this.pending.values()){clearTimeout(job.timer);job.reject(new Error('本地窗口连接已断开，请重新打开工具。'));}
            this.pending.clear();
          });
          const handle=this.window.getNativeWindowHandle();
          this.requiresDetach=true;
          await this.request('attach',{hwnd:handle.readBigUInt64LE().toString(),pid:process.pid});
          return;
        }
        if(!started) {
          const child=spawn(this.executable,[],{cwd:this.root,windowsHide:true,detached:true,stdio:'ignore'});
          child.on('error',()=>{});child.unref();started=true;
        }
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      throw new Error('无法连接本地窗口组件。');
    })().finally(()=>{this.connecting=null;});
    return this.connecting;
  }
  request(command,values={}) {
    return new Promise((resolve,reject)=>{
      if(!this.socket?.writable) {reject(new Error('本地窗口连接已断开。'));return;}
      const id=++this.sequence;
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('本地应用响应超时，请重试。'));},30000);
      this.pending.set(id,{resolve,reject,timer});
      this.socket.write(JSON.stringify({id,command,...values})+'\n');
    });
  }
  layout(bounds,tool,visible) {
    if(this.socket?.writable)this.socket.write(JSON.stringify({command:'layout',bounds,tool:tool||'',visible})+'\n');
  }
  async open(tool) {await this.connect();return this.request('open',{tool});}
  async release(tool) {if(this.socket?.writable)return this.request('release',{tool});}
  async status() {await this.connect();return this.request('status');}
  async detach() {
    if(!this.requiresDetach)return;
    // A timeout or a lost pipe cannot prove cross-process children are safe.
    // Reconnect to the same host and require its verified restore acknowledgement.
    await this.connect();
    const result=await this.request('detach');
    if(result?.detached!==true)throw new Error('未能确认本地应用窗口已安全释放；Research Nexus 将保持运行，请重试退出。');
    this.requiresDetach=false;
    this.socket.end();
  }
};
