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
