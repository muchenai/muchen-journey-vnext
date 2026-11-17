import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
import vm from 'node:vm';

const source=await readFile(new URL('../src/app/project29/useCanvasDialogBounds.ts',import.meta.url),'utf8');
function load(react={}){
  const compiledModule ={exports:{}};
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{module: compiledModule,exports:compiledModule.exports,require:name=>{
    assert.equal(name,'react');return react;
  },...react.environment});
  return compiledModule.exports;
}
const {canvasDialogBounds}=load();
const plain=value=>value===null?null:JSON.parse(JSON.stringify(value));

test('100/75/50/33/25 percent zoom keeps the modal on the same shrinking canvas',()=>{
  // CSS viewport grows when browser zoom shrinks; the existing design bootstrap
  // deliberately preserves the canvas CSS zoom, so its visible height stays 900.
  for(const [zoom,viewportWidth,viewportHeight,left] of [
    [1,1920,900,160],[.75,2560,1200,480],[.5,3840,1800,1120],
    [1/3,5760,2700,2080],[.25,7680,3600,3040],
  ]){
    const actual=plain(canvasDialogBounds({left,top:0,width:1600,height:900},1920,
      {width:viewportWidth,height:viewportHeight}));
    assert.deepEqual(actual,{left,top:0,width:1600,height:900,scale:5/6});
    assert.equal((actual.left+actual.width/2)*zoom,viewportWidth*zoom/2);
    assert.equal(actual.height*zoom,900*zoom);
  }
});

test('enlarged and scrolled canvases bound the modal by their visible intersection',()=>{
  assert.deepEqual(plain(canvasDialogBounds({left:0,top:0,width:1600,height:900},1920,
    {width:1280,height:600})),{left:0,top:0,width:1280,height:600,scale:5/6});
  assert.deepEqual(plain(canvasDialogBounds({left:-300,top:-100,width:1600,height:900},1920,
    {width:1920,height:1080})),{left:0,top:0,width:1300,height:800,scale:5/6});
  assert.deepEqual(plain(canvasDialogBounds({left:100,top:50,width:1600,height:900},1920,
    {width:1280,height:720})),{left:100,top:50,width:1180,height:670,scale:5/6});
});

test('standalone fallback fits the viewport and invalid/unpainted bounds stay closed',()=>{
  assert.deepEqual(plain(canvasDialogBounds(null,0,{width:1024,height:768})),
    {left:0,top:0,width:1024,height:768,scale:1});
  assert.equal(canvasDialogBounds(null,0,{width:0,height:768}),null);
  assert.equal(canvasDialogBounds({left:0,top:0,width:0,height:0},1920,{width:1024,height:768}),null);
  assert.equal(canvasDialogBounds({left:0,top:0,width:1920,height:1080},0,{width:1024,height:768}),null);
  assert.equal(canvasDialogBounds({left:NaN,top:0,width:1920,height:1080},1920,{width:1024,height:768}),null);
  assert.equal(canvasDialogBounds({left:3000,top:0,width:1920,height:1080},1920,{width:1024,height:768}),null);
});

test('hook measures before opening, follows scene changes and cleans observers and queued work',()=>{
  const variables=new Map(),frames=new Map(),listeners=new Map(),resizers=[],mutators=[];
  let effect,ready=false,canvas={offsetWidth:1920,getBoundingClientRect:()=>({left:160,top:0,width:1600,height:900})};
  let nextFrame=1,cancelled=0;
  const dialog={style:{getPropertyValue:name=>variables.get(name)||'',setProperty:(name,value)=>variables.set(name,value),removeProperty:name=>variables.delete(name)},contains:node=>node===dialog};
  class ResizeObserver{
    constructor(callback){this.callback=callback;this.observing=[];resizers.push(this);}
    observe(node){this.observing.push(node);}
    disconnect(){this.observing=[];}
  }
  class MutationObserver{
    constructor(callback){this.callback=callback;this.observing=[];mutators.push(this);}
    observe(...value){this.observing.push(value);}
    disconnect(){this.observing=[];}
  }
  const root={},body={};
  const environment={ResizeObserver,MutationObserver,Node:Object,
    document:{documentElement:root,body,querySelectorAll:()=>canvas?[canvas]:[]},
    window:{innerWidth:1920,innerHeight:900,
      requestAnimationFrame:callback=>{const id=nextFrame++;frames.set(id,callback);return id;},
      cancelAnimationFrame:id=>{cancelled++;frames.delete(id);},
      addEventListener:(name,callback)=>listeners.set(name,callback),
      removeEventListener:(name,callback)=>{if(listeners.get(name)===callback)listeners.delete(name);},
    },
  };
  const {useCanvasDialogBounds}=load({useState:()=>[ready,value=>{ready=value;}],
    useLayoutEffect:callback=>{effect=callback;},environment});
  assert.equal(useCanvasDialogBounds({current:dialog},true),false);
  const cleanup=effect();
  assert.equal(ready,true);
  assert.equal(variables.get('--ex-modal-left'),'160px');
  assert.equal(variables.get('--ex-modal-height'),'900px');
  assert.equal(variables.get('--ex-modal-scale'),String(5/6));
  assert.deepEqual(resizers[0].observing,[canvas]);
  listeners.get('resize')();listeners.get('resize')();mutators[0].callback();
  assert.equal(frames.size,1,'resize and root-style updates share one frame');
  canvas={offsetWidth:1920,getBoundingClientRect:()=>({left:50,top:0,width:1000,height:562.5})};
  const pending=[...frames.values()][0];frames.clear();pending();
  assert.equal(variables.get('--ex-modal-left'),'50px');
  assert.equal(variables.get('--ex-modal-scale'),String(1000/1920));
  assert.deepEqual(resizers[0].observing,[canvas]);
  canvas.getBoundingClientRect=()=>({left:0,top:0,width:0,height:0});
  resizers[0].callback();
  const unpainted=[...frames.values()][0];frames.clear();unpainted();
  assert.equal(ready,false);
  assert.deepEqual(resizers[0].observing,[canvas],'unpainted canvases remain observed until they acquire dimensions');
  canvas.getBoundingClientRect=()=>({left:50,top:0,width:1000,height:562.5});
  resizers[0].callback();
  const painted=[...frames.values()][0];frames.clear();painted();
  assert.equal(ready,true);
  listeners.get('scroll')({target:dialog});assert.equal(frames.size,0,'content scroll needs no scene measurement');
  mutators[1].callback([{target:dialog}]);assert.equal(frames.size,0,'modal mutations do not observe themselves');
  mutators[1].callback([{target:body}]);assert.equal(frames.size,1);
  cleanup();
  assert.equal(cancelled,1);assert.equal(frames.size,0);assert.equal(listeners.size,0);
  assert.equal(variables.size,0);assert.equal(resizers[0].observing.length,0);
  assert.equal(mutators.every(observer=>observer.observing.length===0),true);
  variables.set('--ex-modal-scale','1');
  assert.equal(useCanvasDialogBounds({current:dialog},false),false);
  effect();
  assert.equal(variables.size,0);
});
