// DOM creation alone is not readiness. Decode the complete scene and wait for
// fonts. A hidden iframe may suspend animation frames, so readiness must not
// depend on a paint callback that can only run after the host reveals it.
export const worldMapReadyBridge = `(()=>{
  let started=false;
  const send=type=>parent.postMessage({type},'*');
  const decode=image=>new Promise((resolve,reject)=>{
    const finish=()=>image.naturalWidth ? image.decode().then(resolve,reject) : reject(new Error('map image failed'));
    if(image.complete)finish();
    else {image.addEventListener('load',finish,{once:true});image.addEventListener('error',reject,{once:true})}
  });
  const start=()=>{
    if(started||!document.querySelector('.universe .planet-node'))return;
    started=true;observer.disconnect();
    Promise.all([...Array.from(document.images,decode),document.fonts.ready])
      .then(()=>send('journey-world-map-ready'),()=>send('journey-world-map-error'));
  };
  const observer=new MutationObserver(start);
  observer.observe(document.body,{childList:true,subtree:true});start();
})();`;

export const worldMapVisibilityBridge = `(()=>{
  let active=false,pausedByHost=false;
  const sync=()=>{
    if(!document.querySelector('.planet-node'))return;
    if(!active){const pause=document.querySelector('button[aria-label="暂停动效"]');if(pause&&!pause.disabled){pausedByHost=true;pause.click()}}
    else if(pausedByHost){pausedByHost=false;document.querySelector('button[aria-label="播放动效"]')?.click()}
  };
  addEventListener('message',event=>{
    if(event.source!==parent||event.data?.type!=='journey-world-map-context')return;
    active=Boolean(event.data.active);sync();
  });
  new MutationObserver(sync).observe(document.body,{childList:true,subtree:true});
})();`;

// Reset DOM while hidden without rAF. Only after the parent makes this iframe
// paintable (behind a cover) do we wait for overview frames and acknowledge it.
export const worldMapInstantResetBridge = `(()=>{
  let pending=null,settleTimer=null,paintFrame=null;
  const root=document.documentElement;
  const flush=()=>{
    const universe=document.querySelector('.universe');
    if(!universe)return;
    universe.getBoundingClientRect();
    for(const element of [universe,...universe.querySelectorAll('*')]){
      const style=getComputedStyle(element);
      void style.transform;void style.opacity;void style.filter;void style.scale;void style.rotate;
    }
  };
  const isOverview=()=>{
    const scene=document.querySelector('.cosmos-scene');
    return scene&&!document.querySelector('.universe.has-selection,.planet-detail,.focus-flight,.focus-instruction,.planet-node.is-selected,.planet-node.is-in-flight')
      &&Number(scene.style.getPropertyValue('--zoom'))===1
      &&parseFloat(scene.style.getPropertyValue('--pan-x'))===0
      &&parseFloat(scene.style.getPropertyValue('--pan-y'))===0;
  };
  const check=()=>{
    if(!pending||pending.prepared)return;
    if(!pending.clicked){
      const button=document.querySelector('button[aria-label="重置视图"]');
      if(!button||button.disabled)return;
      pending.clicked=true;flush();button.click();
    }
    if(!isOverview()||settleTimer!==null)return;
    const request=pending;
    // Also allow React's canvas cleanup effects to run after the DOM commit.
    settleTimer=setTimeout(()=>{
      settleTimer=null;
      if(pending!==request||!isOverview())return;
      flush();
      request.prepared=true;
      if(request.requestId===null){
        // Departure is initiated inside this frame, before host navigation.
        // It needs no parent round trip and no visible animation frame.
        pending=null;
      }else{
        parent.postMessage({type:'journey-world-map-reset-complete',requestId:request.requestId},'*');
      }
    },0);
  };
  new MutationObserver(check).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style']});
  const reset=requestId=>{
    if(settleTimer!==null){clearTimeout(settleTimer);settleTimer=null}
    if(paintFrame!==null){cancelAnimationFrame(paintFrame);paintFrame=null}
    pending={requestId,clicked:false,prepared:false,presenting:false};
    root.setAttribute('data-map-resetting','');
    check();
  };
  document.addEventListener('journey-world-map-depart',()=>{
    // Keep the old scene concealed through navigation and until a future
    // presentation is prepared. Reset in this click, not on the next entry.
    root.setAttribute('data-map-departing','');
    reset(null);
  });
  addEventListener('message',event=>{
    if(event.source!==parent||!Number.isSafeInteger(event.data?.requestId))return;
    if(event.data.type==='journey-world-map-present'){
      const request=pending;
      if(!request||!request.prepared||request.presenting||request.requestId!==event.data.requestId)return;
      request.presenting=true;
      root.removeAttribute('data-map-departing');
      flush();
      // The host has committed visibility before sending this request. Two
      // frames give the browser an overview paint while the cover still hides it.
      paintFrame=requestAnimationFrame(()=>{
        paintFrame=null;
        if(pending!==request||!isOverview())return;
        flush();
        paintFrame=requestAnimationFrame(()=>{
          paintFrame=null;
          if(pending!==request||!isOverview())return;
          root.removeAttribute('data-map-resetting');
          flush();
          pending=null;
          parent.postMessage({type:'journey-world-map-presented',requestId:request.requestId},'*');
        });
      });
      return;
    }
    if(event.data.type!=='journey-world-map-reset')return;
    reset(event.data.requestId);
  });
})();`;
