// Electron can receive another quit/close while asynchronous cleanup is pending.
// Only a successful cleanup may authorize destruction of the owning window.
module.exports = function createQuitGuard({cleanup,quit,onStart=()=>{},onError=()=>{}}) {
  let allowed=false,task=null;
  return {
    get allowed(){return allowed;},
    get busy(){return task!==null;},
    handle(event) {
      if(allowed)return;
      event.preventDefault();
      if(task)return task;
      onStart();
      task=Promise.resolve().then(cleanup).then(()=>{
        allowed=true;quit();
      }).catch(error=>{onError(error);}).finally(()=>{task=null;});
      return task;
    }
  };
};
