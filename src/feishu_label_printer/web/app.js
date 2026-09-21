'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="editor-token"]').content;
const clone = value => JSON.parse(JSON.stringify(value));
const kindNames = {text:'文字',barcode:'条码',qr:'二维码',image:'Logo'};
const glyphs = {text:'T',barcode:'▥',qr:'▦',image:'▧'};
const state = {template:null,row:{},selected:null,file:'',dirty:false,history:[],future:[],scale:12,saved:[],version:0,valid:false,image:null};
let presets={},fontNames=[],timer,toastTimer,imageReplace=false;

async function api(path, payload) {
  const response = await fetch(path,{method:payload===undefined?'GET':'POST',headers:{'X-Editor-Token':token,'Content-Type':'application/json'},body:payload===undefined?undefined:JSON.stringify(payload)});
  if(!response.ok){const data=await response.json();throw Error(data.error||'请求失败');}
  return response.json();
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function selected(){return state.template.elements.find(e=>e.id===state.selected);}
function checkpoint(){state.history.push(clone(state.template));if(state.history.length>60)state.history.shift();state.future=[];}
function changed(){state.dirty=true;sync();schedule();persist();}
function edit(fn){const before=clone(state.template);fn();if(JSON.stringify(before)===JSON.stringify(state.template))return;state.history.push(before);if(state.history.length>60)state.history.shift();state.future=[];changed();}
function persist(){try{localStorage.setItem('label-studio-draft-v1',JSON.stringify({template:state.template,row:state.row,file:state.file,dirty:state.dirty}));}catch{}}
function select(id){state.selected=id;syncElements();syncInspector();drawOverlays();}
function option(value,text){const node=document.createElement('option');node.value=value;node.textContent=text;return node;}
function updateSaved(items){state.saved=items;$('savedTemplates').replaceChildren(option('','已保存的模板…'),...items.map(s=>option(s.file,s.file)));if(items.some(s=>s.file===state.file))$('savedTemplates').value=state.file;}
function load(template,file=''){
  state.template=clone(template);state.file=file;state.selected=template.elements[0]?.id||null;state.dirty=false;state.history=[];state.future=[];
  sync();syncData();schedule();persist();
}
function safeToLoad(){return !state.dirty||confirm('当前修改尚未保存，是否切换模板？');}
function sync(){
  const p=state.template.page,m=p.margins_mm||{};
  $('templateName').value=state.template.name;$('dirtyMark').textContent=state.dirty?'有未保存修改':state.file?'已保存':'示例模板';
  const values={pageWidth:p.width_mm,pageHeight:p.height_mm,pageDpi:p.dpi||300,marginLeft:m.left||0,marginRight:m.right||0,marginTop:m.top||0,marginBottom:m.bottom||0,offsetX:p.offset_x_mm||0,offsetY:p.offset_y_mm||0};
  Object.entries(values).forEach(([id,value])=>{if(document.activeElement!==$(id))$(id).value=value;});
  $('pageSummary').textContent=`${p.width_mm} × ${p.height_mm} mm`;$('dpiSummary').textContent=`${p.dpi||300} dpi`;
  $('paperDimensions').textContent=`${p.width_mm} × ${p.height_mm} mm`;
  $('undo').disabled=!state.history.length;$('redo').disabled=!state.future.length;
  $('emptyHint').hidden=state.template.elements.some(e=>e.enabled!==false);
  syncElements();syncInspector();drawOverlays();
}
function syncElements(){
  $('elementCount').textContent=state.template.elements.length;
  $('elements').replaceChildren(...state.template.elements.map(e=>{
    const div=document.createElement('div');div.className='element-row'+(e.id===state.selected?' active':'')+(e.enabled===false?' off':'');
    div.tabIndex=0;div.setAttribute('role','button');div.setAttribute('aria-label',`选择元素 ${e.name||kindNames[e.type]}`);
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=e.enabled!==false;checkbox.setAttribute('aria-label',`打印 ${e.name||e.id}`);
    checkbox.onclick=ev=>ev.stopPropagation();checkbox.onchange=()=>edit(()=>e.enabled=checkbox.checked);
    const glyph=document.createElement('span');glyph.className='glyph';glyph.textContent=glyphs[e.type];
    const info=document.createElement('div');info.className='element-info';const title=document.createElement('strong');title.textContent=e.name||kindNames[e.type];
    const source=document.createElement('small');source.textContent=e.type==='image'?'嵌入图片':e.source?.kind==='field'?`字段 · ${e.source.key}`:`固定 · ${e.source?.value||''}`;
    info.append(title,source);div.append(checkbox,glyph,info);div.onclick=()=>select(e.id);div.onkeydown=ev=>{if(ev.key==='Enter')select(e.id);};return div;
  }));
}
function syncInspector(){
  const e=selected();$('selectHint').hidden=!!e;$('elementControls').hidden=!e;$('selectedBadge').textContent=e?kindNames[e.type]:'未选择';
  $('selectionStatus').textContent=e?`${e.name||e.id} · 拖动移动 / 右下角调整尺寸`:'模板保存在本机 templates 文件夹';
  if(!e)return;
  const values={elementName:e.name||'',elementType:e.type,sourceKind:e.source?.kind||'field',sourceValue:e.source?.value||'',elementX:e.x_mm||0,elementY:e.y_mm||0,elementWidth:e.width_mm,elementHeight:e.height_mm,fontFamily:e.font||'text',fontSize:e.font_size_pt||7,textAlign:e.align||'left'};
  Object.entries(values).forEach(([id,value])=>{if(document.activeElement!==$(id))$(id).value=value;});
  const fields=[...new Set([...Object.keys(state.row),...(e.source?.key?[e.source.key]:[])])];
  $('sourceField').replaceChildren(...fields.map(f=>option(f,f)));$('sourceField').value=e.source?.key||fields[0]||'';
  const image=e.type==='image',text=e.type==='text',barcode=e.type==='barcode';
  $('sourceControls').hidden=image;$('fieldLabel').hidden=e.source?.kind==='literal';$('literalLabel').hidden=e.source?.kind!=='literal';
  $('fontControls').hidden=!text&&!barcode;$('alignLabel').hidden=!text;$('wrapLabel').hidden=!text;$('barcodeTextLabel').hidden=!barcode;
  $('textWrap').checked=e.wrap!==false;$('barcodeText').checked=e.show_text!==false;$('qrHint').hidden=e.type!=='qr';$('replaceImage').hidden=!image;
  // Image elements are created through import, not by changing another element to an empty image.
  $('elementType').querySelector('[value=image]').disabled=!image;
}
function drawOverlays(){
  const p=state.template.page,m=p.margins_mm||{},scale=state.scale;
  const left=(m.left||0)+(p.offset_x_mm||0),top=(m.top||0)+(p.offset_y_mm||0);
  $('paper').style.width=p.width_mm*scale+'px';$('paper').style.height=p.height_mm*scale+'px';
  Object.assign($('marginGuide').style,{left:(m.left||0)*scale+'px',top:(m.top||0)*scale+'px',width:Math.max(0,p.width_mm-(m.left||0)-(m.right||0))*scale+'px',height:Math.max(0,p.height_mm-(m.top||0)-(m.bottom||0))*scale+'px'});
  $('marginGuide').hidden=!$('showGuides').checked;
  $('overlays').replaceChildren(...state.template.elements.filter(e=>e.enabled!==false).map(e=>{
    const div=document.createElement('div');div.className='overlay'+(state.selected===e.id?' selected':'');div.dataset.id=e.id;
    Object.assign(div.style,{left:(left+(e.x_mm||0))*scale+'px',top:(top+(e.y_mm||0))*scale+'px',width:e.width_mm*scale+'px',height:e.height_mm*scale+'px'});
    const tag=document.createElement('span');tag.className='overlay-label';tag.textContent=e.name||kindNames[e.type];div.append(tag);
    if(e.id===state.selected){const handle=document.createElement('span');handle.className='resize';div.append(handle);}
    div.onpointerdown=ev=>startDrag(ev,e);return div;
  }));
}
function startDrag(event,element){
  if(event.button!==0)return;event.preventDefault();event.stopPropagation();
  const resize=event.target.classList.contains('resize'),origin=clone(element),x=event.clientX,y=event.clientY;
  select(element.id);let moved=false;
  const move=ev=>{
    const dx=(ev.clientX-x)/state.scale,dy=(ev.clientY-y)/state.scale;
    if(!moved&&Math.abs(dx)+Math.abs(dy)<.05)return;
    if(!moved){checkpoint();moved=true;}
    const m=state.template.page.margins_mm||{},p=state.template.page;
    const maxw=p.width_mm-(m.left||0)-(m.right||0),maxh=p.height_mm-(m.top||0)-(m.bottom||0);
    const round=v=>Math.round(v*10)/10;
    if(resize){element.width_mm=round(Math.max(.5,Math.min(maxw-origin.x_mm,origin.width_mm+dx)));element.height_mm=round(Math.max(.5,Math.min(maxh-origin.y_mm,origin.height_mm+dy)));}
    else{element.x_mm=round(Math.max(0,Math.min(Math.max(0,maxw-element.width_mm),origin.x_mm+dx)));element.y_mm=round(Math.max(0,Math.min(Math.max(0,maxh-element.height_mm),origin.y_mm+dy)));}
    drawOverlays();syncInspector();
  };
  const end=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);if(moved)changed();};
  window.addEventListener('pointermove',move);window.addEventListener('pointerup',end);window.addEventListener('pointercancel',end);
}
function syncData(){
  $('dataFields').replaceChildren(...Object.entries(state.row).map(([key,value])=>{
    const label=document.createElement('label');label.textContent=key;const input=document.createElement('input');input.value=typeof value==='object'?JSON.stringify(value):value??'';input.setAttribute('aria-label',`预览 ${key}`);
    input.oninput=()=>{state.row[key]=input.value;schedule();persist();};label.append(input);return label;
  }));
}
function schedule(){state.valid=false;$('downloadPng').disabled=true;$('downloadZpl').disabled=true;const version=++state.version;clearTimeout(timer);$('renderStatus').textContent='正在生成打印预览…';timer=setTimeout(()=>render(version),200);}
async function render(version){
  try{
    const result=await api('/api/render',{template:state.template,row:state.row});if(version!==state.version)return;
    state.image=result.image;state.valid=true;$('preview').src=result.image;$('preview').hidden=false;$('previewError').hidden=true;
    $('downloadPng').disabled=false;$('downloadZpl').disabled=!!result.warnings.length;
    $('renderStatus').className=result.warnings.length?'warning':'';
    $('renderStatus').textContent=result.warnings.length?result.warnings.join('；'):`布局检查通过 · ${result.width} × ${result.height} 打印点`;
  }catch(error){if(version!==state.version)return;state.valid=false;$('preview').hidden=true;$('previewError').hidden=false;$('previewError').textContent='请调整布局后查看预览';$('renderStatus').className='error';$('renderStatus').textContent=error.message;}
}
function add(type,extra={}){
  const field=Object.keys(state.row)[0]||'字段';const p=state.template.page,m=p.margins_mm||{};
  const maxw=p.width_mm-(m.left||0)-(m.right||0),maxh=p.height_mm-(m.top||0)-(m.bottom||0);
  const defaults={text:[Math.min(26,maxw),Math.min(4,maxh)],barcode:[maxw,Math.min(8,maxh)],qr:[Math.min(15,maxw,maxh),Math.min(15,maxw,maxh)],image:[Math.min(12,maxw),Math.min(5,maxh)]};
  const e={id:crypto.randomUUID(),name:kindNames[type],type,enabled:true,x_mm:0,y_mm:0,width_mm:defaults[type][0],height_mm:defaults[type][1],source:{kind:'field',key:field},font:'text',font_size_pt:type==='barcode'?5.5:7,align:'left',wrap:true,show_text:true,...extra};
  edit(()=>{state.template.elements.push(e);state.selected=e.id;});
}
function download(name,blob){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function fileStem(){return state.template.name.replace(/[^\p{L}\p{N}_ -]/gu,'-').slice(0,80)||'label-template';}
async function save(){
  const name=$('saveName').value.trim();$('saveError').textContent='';
  if(name!==state.file&&state.saved.some(s=>s.file===name)&&!confirm('同名模板已存在，是否覆盖？'))return;
  try{const result=await api('/api/templates',{name,template:state.template});state.file=result.file;state.dirty=false;updateSaved(result.saved);$('saveDialog').close();sync();persist();toast('模板已保存，可用于打印队列');}
  catch(error){$('saveError').textContent=error.message;}
}
function undo(redo=false){const from=redo?state.future:state.history,to=redo?state.history:state.future;if(!from.length)return;to.push(clone(state.template));state.template=from.pop();state.dirty=true;sync();schedule();persist();}
function bindElement(id,key,convert=value=>value){$(id).onchange=()=>{const e=selected();if(e)edit(()=>e[key]=convert($(id).value));};}
function bindPage(id,key){$(id).onchange=()=>{if($(id).value==='')return;const value=Number($(id).value);if(Number.isFinite(value))edit(()=>state.template.page[key]=value);};}

async function init(){
  let draft;try{draft=JSON.parse(localStorage.getItem('label-studio-draft-v1'));}catch{}
  const bootstrap=await api('/api/bootstrap');presets=bootstrap.templates;fontNames=bootstrap.fonts;state.row=bootstrap.sample;updateSaved(bootstrap.saved);
  $('fontFamily').replaceChildren(...fontNames.map(key=>option(key,{text:'中文 / 常规',mono:'等宽',dot:'点阵 Doto'}[key]||key)));
  load(presets.material);
  // Offer recovery explicitly: never silently replace the sample or saved template.
  $('preset').onchange=()=>{if(safeToLoad())load(presets[$('preset').value]);};
  $('loadTemplate').onclick=async()=>{const name=$('savedTemplates').value;if(!name)return toast('先选择一个已保存模板');if(!safeToLoad())return;try{load((await api('/api/templates?name='+encodeURIComponent(name))).template,name);}catch(e){toast(e.message);}};
  $('templateName').onchange=()=>edit(()=>state.template.name=$('templateName').value.trim()||'新标签');
  for(const [id,key] of Object.entries({pageWidth:'width_mm',pageHeight:'height_mm',pageDpi:'dpi',offsetX:'offset_x_mm',offsetY:'offset_y_mm'}))bindPage(id,key);
  for(const side of ['Left','Right','Top','Bottom'])$('margin'+side).onchange=()=>edit(()=>{state.template.page.margins_mm||={};state.template.page.margins_mm[side.toLowerCase()]=Number($('margin'+side).value);});
  for(const [id,key] of Object.entries({elementName:'name',fontFamily:'font',textAlign:'align'}))bindElement(id,key);
  for(const [id,key] of Object.entries({elementX:'x_mm',elementY:'y_mm',elementWidth:'width_mm',elementHeight:'height_mm',fontSize:'font_size_pt'}))bindElement(id,key,Number);
  $('elementType').onchange=()=>{const e=selected();edit(()=>{e.type=$('elementType').value;if(e.type==='qr'){const p=state.template.page,m=p.margins_mm||{};const size=Math.min(15,p.width_mm-(m.left||0)-(m.right||0)-e.x_mm,p.height_mm-(m.top||0)-(m.bottom||0)-e.y_mm);e.width_mm=e.height_mm=Math.max(.5,size);}e.source||={kind:'field',key:Object.keys(state.row)[0]||'字段'};});};
  $('sourceKind').onchange=()=>{const e=selected();edit(()=>{e.source=$('sourceKind').value==='field'?{kind:'field',key:Object.keys(state.row)[0]||'字段'}:{kind:'literal',value:'文字内容'};});};
  $('sourceField').onchange=()=>{const e=selected();edit(()=>e.source={kind:'field',key:$('sourceField').value});};
  $('sourceValue').onchange=()=>{const e=selected();edit(()=>e.source={kind:'literal',value:$('sourceValue').value});};
  $('textWrap').onchange=()=>{const e=selected();edit(()=>e.wrap=$('textWrap').checked);};$('barcodeText').onchange=()=>{const e=selected();edit(()=>e.show_text=$('barcodeText').checked);};
  document.querySelectorAll('[data-add]').forEach(button=>button.onclick=()=>add(button.dataset.add));
  $('duplicate').onclick=()=>{const e=selected();if(e)add(e.type,{...clone(e),id:crypto.randomUUID(),name:(e.name||'元素')+' 副本'});};
  $('remove').onclick=()=>{const e=selected();if(e)edit(()=>{state.template.elements=state.template.elements.filter(item=>item.id!==e.id);state.selected=null;});};
  $('undo').onclick=()=>undo();$('redo').onclick=()=>undo(true);
  $('zoom').onchange=()=>{state.scale=Number($('zoom').value);drawOverlays();};$('showGuides').onchange=drawOverlays;
  $('fit').onclick=()=>{state.scale=Math.min(20,Math.max(2,Math.min(($('stage').clientWidth-100)/state.template.page.width_mm,($('stage').clientHeight-100)/state.template.page.height_mm)));drawOverlays();};
  $('paper').onpointerdown=ev=>{if(ev.target.id==='paper'||ev.target.id==='overlays')select(null);};
  $('save').onclick=()=>{$('saveName').value=state.file||fileStem();$('saveError').textContent='';$('saveDialog').showModal();};$('confirmSave').onclick=save;
  $('exportTemplate').onclick=()=>download(fileStem()+'.json',new Blob([JSON.stringify(state.template,null,2)],{type:'application/json'}));
  $('downloadPng').onclick=()=>{if(state.valid){const bytes=Uint8Array.from(atob(state.image.split(',')[1]),c=>c.charCodeAt(0));download(fileStem()+'.png',new Blob([bytes],{type:'image/png'}));}};
  $('downloadZpl').onclick=async()=>{try{const response=await fetch('/api/export-zpl',{method:'POST',headers:{'Content-Type':'application/json','X-Editor-Token':token},body:JSON.stringify({template:state.template,row:state.row})});if(!response.ok)throw Error((await response.json()).error);download(fileStem()+'.zpl',await response.blob());}catch(e){toast(e.message);}};
  $('importTemplate').onclick=()=>$('templateFile').click();$('templateFile').onchange=async()=>{const file=$('templateFile').files[0];if(!file)return;try{if(file.size>6_000_000)throw Error('模板文件超过6MB');const template=JSON.parse(await file.text());await api('/api/validate',{template});if(safeToLoad()){load(template);state.dirty=true;sync();}}catch(e){toast('导入失败：'+e.message);}finally{$('templateFile').value='';}};
  $('importData').onclick=()=>{$('dataJson').value=JSON.stringify(state.row,null,2);$('dataError').textContent='';$('dataDialog').showModal();};
  $('confirmData').onclick=()=>{try{const row=JSON.parse($('dataJson').value);if(!row||typeof row!=='object'||Array.isArray(row))throw Error('请输入JSON对象');if(Object.keys(row).length>100)throw Error('最多100个字段');state.row=row;syncData();syncInspector();schedule();persist();$('dataDialog').close();}catch(e){$('dataError').textContent=e.message;}};
  $('addField').onclick=()=>{const name=prompt('新字段名称');if(!name?.trim())return;state.row[name.trim()]='';syncData();syncInspector();persist();};
  $('addImage').onclick=()=>{imageReplace=false;$('imageFile').click();};$('replaceImage').onclick=()=>{imageReplace=true;$('imageFile').click();};
  $('imageFile').onchange=async()=>{
    const file=$('imageFile').files[0];if(!file)return;
    let url;try{if(file.size>2_000_000)throw Error('图片须小于2MB');url=URL.createObjectURL(file);const img=new Image();img.src=url;await img.decode();if(!img.width||!img.height)throw Error('无效图片');
      const scale=Math.min(1,1024/Math.max(img.width,img.height));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(img.width*scale));canvas.height=Math.max(1,Math.round(img.height*scale));const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/png');
      if(imageReplace&&selected())edit(()=>selected().data_url=data);else add('image',{data_url:data,name:'Logo'});
    }catch(e){toast('图片导入失败：'+e.message);}finally{if(url)URL.revokeObjectURL(url);$('imageFile').value='';}
  };
  window.addEventListener('keydown',ev=>{
    if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='s'){ev.preventDefault();$('save').click();}
    if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){ev.preventDefault();undo(ev.shiftKey);}
  });
  window.addEventListener('beforeunload',ev=>{if(state.dirty){ev.preventDefault();ev.returnValue='';}});
  // Apply edits immediately: spinner changes, keyboard typing and browser fill all emit input.
  document.querySelectorAll('input:not([type=file]):not([type=checkbox]),textarea').forEach(el=>el.addEventListener('input',()=>{
    if(el.type==='number'&&(el.value===''||!Number.isFinite(Number(el.value))))return;
    if(el.onchange)el.onchange();
  }));
  if(draft?.dirty&&confirm('检测到上次未保存的排版，是否恢复？')){
    try{await api('/api/validate',{template:draft.template});state.row=draft.row||state.row;load(draft.template,draft.file||'');state.dirty=true;sync();persist();toast('已恢复未保存的排版');}catch(e){toast('恢复失败：'+e.message);}
  }
}
init().catch(error=>{$('renderStatus').className='error';$('renderStatus').textContent='启动失败：'+error.message;});
