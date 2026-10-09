'use strict';
const root = document.getElementById('app');
const modal = document.getElementById('modal');
const state = {user:null, role:'employee', page:'new', files:{}, list:[], current:null, filter:'all', search:'', previous:null, submitting:false, timer:null, applicant:'', sample:false};
const slots = {
  contract:'劳动合同', identity:'身份证', social:'社保缴纳记录', property:'无房产证明',
  diploma:'学历证书', degree:'学位证书', education_report:'学信网学历验证报告', degree_report:'学信网学位验证报告'
};
const statuses = {queued:'排队中',processing:'正在预审',returned:'待补正',review:'待人工复核',approved:'企业预审通过',pass:'符合已检规则',fail:'需补正'};
const esc = x => String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const size = bytes => bytes<1048576?`${Math.ceil(bytes/1024)} KB`:`${(bytes/1048576).toFixed(1)} MB`;
const date = value => new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
const badge = status => `<span class="badge ${esc(status)}">${icon(status==='approved'||status==='pass'?'check':status==='returned'||status==='fail'?'circle-alert':'clock-3')}${statuses[status]||esc(status)}</span>`;
function icons(){if(window.lucide) window.lucide.createIcons();}
function toast(message){const el=document.getElementById('toast');el.textContent=message;el.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.hidden=true,5500);}
async function api(path, options={}){
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  const data=await response.json();
  if(!response.ok){
    if(response.status===401 && state.user){state.user=null;clearTimeout(state.timer);renderLogin();}
    throw new Error(data.error||'请求失败');
  }
  return data;
}
function header(){
  return `<header class="topbar"><div class="brand"><span class="brand-mark">${icon('file-check-2')}</span>审核工作台<span class="brand-meta">2026 · 企业预审</span></div><div class="top-actions"><span class="pilot">本机试用版</span>${state.user?`<span class="avatar">${state.user.role==='hr'?'HR':'员'}</span><span class="user-name small">${esc(state.user.name)}</span><button class="btn icon" data-action="logout" aria-label="退出登录" title="退出登录">${icon('log-out')}</button>`:''}</div></header>`;
}
function renderLogin(){
  root.innerHTML=header()+`<main class="login-wrap"><div class="login-title"><h1>审核工作台</h1><p>2026 海淀区应届生住房补贴 · 企业预审</p></div><div class="roles" role="tablist" aria-label="登录身份"><button class="role ${state.role==='hr'?'active':''}" role="tab" aria-selected="${state.role==='hr'}" data-action="role" data-role="hr">${icon('briefcase-business')}HR 入口</button><button class="role ${state.role==='employee'?'active':''}" role="tab" aria-selected="${state.role==='employee'}" data-action="role" data-role="employee">${icon('user-round')}员工入口</button></div><form id="login-form" class="login-form"><label class="field"><span>企业账号</span><input name="username" autocomplete="username" placeholder="请输入账号" required></label><label class="field"><span>密码</span><span class="password-input"><input type="password" name="password" autocomplete="current-password" placeholder="请输入密码" required><button type="button" class="btn icon" data-action="password" aria-label="显示密码" title="显示密码">${icon('eye')}</button></span></label><p id="login-error" class="error" role="alert" hidden></p><button type="submit" class="btn primary">登录${icon('arrow-right')}</button><div class="login-demo"><span>本地体验账号<br><strong>${state.role==='hr'?'hr':'employee'}</strong> / ${state.role==='hr'?'Hr2026!':'Employee2026!'}</span><button type="button" class="text-btn" data-action="fill-login">填入账号${icon('arrow-up-right')}</button></div></form><p class="login-footer">仅限本机试用 · 不对公网开放<br>材料存储在当前电脑，未接入外部大模型</p></main>`;
  icons();
}
let lastRenderedPage=null;
function shell(content){
  const hr=state.user.role==='hr';
  const nav=(page,label,ico)=>`<button class="nav-item ${state.page===page?'active':''}" data-action="nav" data-page="${page}">${icon(ico)}${label}</button>`;
  const previousColumn=root.querySelector('.content-column');
  const keepScroll=previousColumn&&lastRenderedPage===state.page?previousColumn.scrollTop:0;
  root.innerHTML=header()+`<div class="shell"><nav class="sidebar" aria-label="工作空间"><div class="nav-label">${hr?'人力资源':'员工工作空间'}</div>${!hr?nav('new','材料提交','folder-up'):''}${nav('list',hr?'审核队列':'我的申请',hr?'list-checks':'files')}${nav('messages','消息记录','bell')}${hr?nav('rules','审核规则','sliders-horizontal'):''}<div class="sidebar-bottom"><strong>2026 年度</strong><br>海淀区住房补贴<br><br>${icon('hard-drive')}本地存储 · 本地识别</div></nav><div class="content-column"><main class="workspace">${content}</main></div></div>`;
  const column=root.querySelector('.content-column');
  if(column)column.scrollTop=keepScroll;
  lastRenderedPage=state.page;
  icons();
}
function steps(active){
  return `<div class="steps">${['材料上传','自动预审','结果处理'].map((label,i)=>`${i?'<div class="step-line"></div>':''}<div class="step ${i===active?'active':i<active?'done':''}"><b>${i<active?'✓':i+1}</b>${label}</div>`).join('')}</div>`;
}
function chosen(slot){return state.files[slot]||[];}
function slotControl(slot,edu=false){
  const files=chosen(slot);
  return `<div>${edu?`<div class="slot-label">${slots[slot]}</div>`:''}<div class="upload-control"><div class="file-area">${files.length?files.map((f,i)=>`<div class="file-pill">${icon('file-text')}<span class="filename" title="${esc(f.name)}">${esc(f.name)}</span><small>${size(f.size)}</small><button class="btn icon" data-action="remove-file" data-slot="${slot}" data-index="${i}" aria-label="移除${esc(f.name)}" title="移除文件">${icon('x')}</button></div>`).join(''):'<span class="muted small">未选择文件</span>'}</div><label class="btn select-file" title="${slots[slot]}">${icon(files.length?'plus':'upload')}<span>${files.length?'添加':'选择文件'}</span><input class="file-picker" type="file" accept=".pdf,.jpg,.jpeg,.png" multiple data-slot="${slot}" aria-label="选择${slots[slot]}"></label></div></div>`;
}
function form(){
  const complete=Object.keys(slots).filter(s=>chosen(s).length).length;
  const catCount=['contract','identity','social','property'].filter(s=>chosen(s).length).length + (['diploma','degree','education_report','degree_report'].every(s=>chosen(s).length)?1:0);
  const missing=Object.keys(slots).filter(s=>!chosen(s).length);
  shell(`<div class="page-heading"><div><div class="eyebrow">EMPLOYEE / 2026</div><h1>${state.previous?'补正申请材料':'住房补贴申请'}</h1><p>2026 年度 / 海淀区 / 企业预审</p></div><div class="heading-actions">${state.sample?'<span class="sample-tag">测试材料 · 非真实申请</span>':''}<button class="btn" data-action="samples" ${state.submitting?'disabled':''}>${icon('flask-conical')}载入测试材料</button></div></div>${steps(0)}<form id="application-form"><div class="form-meta"><label class="field"><span>申请人姓名</span><input id="applicant" name="applicant" maxlength="40" minlength="2" value="${esc(state.applicant)}" required placeholder="与证件姓名一致" ${state.submitting?'disabled':''}></label>${state.previous?`<span class="small muted">原申请：${esc(state.previous)}</span>`:''}</div><div class="section-heading"><h2>申请材料</h2><span class="complete"><span class="meter"><span style-fallback="${complete}"></span></span>已选齐 ${catCount} / 5 类 · ${complete} / 8 项</span></div><div class="upload-section">${['contract','identity','social','property'].map((slot,i)=>`<section class="material-row"><div class="material-label"><span class="doc-symbol">${icon(['file-signature','contact-round','calendar-range','house'][i])}</span><div><h3>${slots[slot]}</h3><small>0${i+1}</small></div></div>${slotControl(slot)}</section>`).join('')}<section class="material-row"><div class="material-label"><span class="doc-symbol">${icon('graduation-cap')}</span><div><h3>学历学位证明</h3><small>05</small></div></div><div class="edu-grid">${['diploma','degree','education_report','degree_report'].map(s=>slotControl(s,true)).join('')}</div></section></div><div class="form-bottom"><div class="limits">PDF / JPG / PNG · 单文件 ≤ 15 MB<br>整套 ≤ 45 MB、60 页 · 可在多个材料项选择同一份合并文件</div><div class="submit-wrap"><span class="missing" id="missing-materials">${missing.length?`还缺 ${missing.length} 项必需材料`:'所有必需材料已选择'}</span><button class="btn primary" type="submit" ${complete<8||state.submitting?'disabled':''}>${icon(state.submitting?'loader-circle':'send')}${state.submitting?'正在上传…':'上传并预审'}</button></div></div><div class="local-notice">${icon('shield-check')}<span>尚未提交的文件仅暂存在当前页面；刷新或退出将清空。提交后保存在本机。</span></div></form>`);
  const meter=root.querySelector('.meter span'); if(meter)meter.style.width=`${complete/8*100}%`;
  if(state.submitting)root.querySelectorAll('input,button[data-action="remove-file"]').forEach(el=>el.disabled=true);
}
function filteredList(){
  return state.list.filter(a=>(state.filter==='all'||a.status===state.filter)&&(!state.search||`${a.applicant} ${a.id}`.toLowerCase().includes(state.search.toLowerCase())));
}
function tableRows(){
  const items=filteredList();
  if(!items.length)return `<div class="empty">${icon('inbox')}<h2>${state.list.length?'没有匹配的申请':'暂无申请记录'}</h2><p>${state.list.length?'请调整搜索或状态筛选。':'提交材料后，审核记录将出现在这里。'}</p>${state.user.role==='employee'?'<button class="btn primary" data-action="nav" data-page="new">新建申请</button>':''}</div>`;
  return `<table><thead><tr><th>申请人 / 编号</th><th>提交时间</th><th>审核状态</th><th>问题项</th><th>操作</th></tr></thead><tbody>${items.map(a=>`<tr><td><strong>${esc(a.applicant)}</strong><small>${esc(a.id)}</small>${a.previous?'<small>补正版本</small>':''}</td><td>${date(a.created)}</td><td>${badge(a.status)}</td><td>${a.issues||'—'}</td><td><button class="text-btn" data-action="detail" data-id="${a.id}">${state.user.role==='hr'?'查看审核':'查看详情'}${icon('arrow-up-right')}</button></td></tr>`).join('')}</tbody></table>`;
}
function list(){
  const hr=state.user.role==='hr';
  shell(`<div class="page-heading"><div><div class="eyebrow">${hr?'HUMAN RESOURCES':'EMPLOYEE'} / 2026</div><h1>${hr?'材料审核队列':'我的申请'}</h1><p>海淀区住房补贴 · 企业内部预审</p></div><div class="heading-actions"><button class="btn" data-action="refresh">${icon('refresh-cw')}刷新</button>${!hr?'<button class="btn primary" data-action="nav" data-page="new">新建申请</button>':''}</div></div><div class="list-stats"><div><b>${state.list.length}</b>全部申请</div><div><b>${state.list.filter(a=>a.status==='review').length}</b>待人工复核</div><div><b>${state.list.filter(a=>a.status==='returned').length}</b>待补正</div></div><div class="toolbar"><div class="filters" role="group" aria-label="状态筛选">${[['all','全部'],['review','待复核'],['returned','待补正'],['approved','已通过']].map(([v,label])=>`<button class="filter ${state.filter===v?'active':''}" data-action="filter" data-value="${v}" aria-pressed="${state.filter===v}">${label}</button>`).join('')}</div><input class="search" type="search" id="search" placeholder="搜索姓名或申请编号" aria-label="搜索申请" value="${esc(state.search)}"></div><div id="list-table" class="table-wrap">${tableRows()}</div>`);
}
const checkGroups = [
  {status:'fail',label:'待补正',symbol:'circle-alert'},
  {status:'pass',label:'已通过检查',symbol:'circle-check'},
  {status:'review',label:'待人工复核',symbol:'clock-3'}
];
function resultOverview(app){
  return `<div class="section-heading"><h2>审核结果</h2><span class="small muted">${app.checks.length} 项检查</span></div><div class="result-overview">${checkGroups.map(group=>{
    const count=app.checks.filter(check=>check.status===group.status).length;
    return `<button class="result-entry ${group.status}" data-action="check-group" data-status="${group.status}" ${count?'':'disabled'}><span class="result-entry-label">${icon(group.symbol)}${group.label}</span><span class="result-entry-count">${count} 项${icon('chevron-right')}</span></button>`;
  }).join('')}</div>`;
}
function checkGroup(status){
  const group=checkGroups.find(item=>item.status===status);
  if(!group)return;
  clearTimeout(state.timer);
  state.page='check-group';
  const app=state.current;
  const entries=app.checks.map((check,index)=>({check,index})).filter(item=>item.check.status===status);
  shell(`<div class="page-heading"><div><button class="text-btn small" data-action="back-detail">${icon('arrow-left')}返回结果概览</button><h1>${group.label}详情</h1><p>${esc(app.applicant)} · ${esc(app.id)}</p></div><span class="badge ${status}">${entries.length} 项检查</span></div><div class="checks">${entries.map(({check,index})=>`<article class="check-row"><h3>${esc(check.title)}</h3><div class="check-result">${badge(check.status)}<p>${esc(check.reason)}</p></div>${check.evidence.length?`<button class="text-btn evidence-button" data-action="evidence" data-index="${index}">查看依据</button>`:'<span></span>'}</article>`).join('')}</div>`);
}
function detail(){
  const a=state.current, hr=state.user.role==='hr', processing=['queued','processing'].includes(a.status);
  const fails=a.checks.filter(c=>c.status==='fail');
  const titles={returned:`材料已退回 · ${fails.length?fails.length+' 项检查需补正':'请查看复核意见'}`,review:'自动识别已完成 · 等待人工复核',approved:'企业预审通过',queued:'材料已提交 · 排队处理中',processing:'正在识别材料'};
  let main=processing?`<div class="progress-block">${icon('scan-text')}<h2>${titles[a.status]}</h2><p>已处理 ${a.progress} / ${a.documents.length} 份文件</p><progress value="${a.progress}" max="${a.documents.length}" aria-label="识别进度"></progress><p class="small">本地处理 · 无需停留在此页面</p></div>`:
    `<div class="banner ${a.status}">${icon(a.status==='approved'?'circle-check':'clipboard-check')}<div><h2>${titles[a.status]}</h2><p>${a.status==='returned'?'其他材料已保留，补正后可重新提交。':a.status==='approved'?'企业内部预审结果，不代表政府审批通过。':'材料类型和内容检查不等同于权威验真。'}</p></div></div>${a.error?`<p class="review-note">${esc(a.error)}</p>`:''}${a.decision?`<div class="review-note"><strong>HR 复核意见</strong><br>${esc(a.decision)}</div>`:''}${resultOverview(a)}`;
  shell(`<div class="page-heading"><div><button class="text-btn small" data-action="nav" data-page="list">${icon('arrow-left')}返回申请列表</button><h1>${esc(a.applicant)} · 住房补贴申请</h1><p>${esc(a.id)} · ${date(a.created)}</p></div>${badge(a.status)}</div>${steps(processing?1:2)}<div class="detail-columns"><section>${main}<div class="detail-actions">${!processing&&hr&&['review','returned'].includes(a.status)?'<button class="btn primary" data-action="decision" data-status="approved">确认预审通过</button><button class="btn danger" data-action="decision" data-status="returned">退回补正</button>':''}${a.status==='returned'&&!hr?'<button class="btn primary" data-action="correct">补正材料</button><button class="btn" data-action="appeal">申请人工复核</button>':''}</div></section><aside class="aside-detail"><section class="side-section"><h3>已上传材料</h3><div class="doc-list">${a.documents.map(d=>`<button data-action="preview" data-file="${d.id}" ${d.pages.length?'':'disabled'}>${icon('file-text')}<span title="${esc(d.name)}">${esc(d.name)}</span><small>${d.pages.length} 页</small></button>`).join('')}</div></section><section class="side-section"><h3>处理记录</h3><div class="timeline">${[...a.events].reverse().map(e=>`<div class="timeline-item"><small>${date(e.time)}</small><p><strong>${esc(e.actor)}</strong><br>${esc(e.text)}</p></div>`).join('')}</div></section><section class="side-section small muted">规则版本<br>${esc(a.version)}</section></aside></div>`);
  if(processing){clearTimeout(state.timer);state.timer=setTimeout(async()=>{try{if(state.page!=='detail')return;state.current=await api(`/api/applications/${a.id}`);detail();}catch(e){toast(e.message);}},2200);}
}
function rules(){
  const rows=[
    ['上传完整性','五类材料、八个必需子项全部选择后，才能上传。服务端再次校验。合并文件可复用，不以文件数量替代材料完整性。'],
    ['劳动合同','明确的合同起始年份为 2026 年；未可靠定位日期时转人工。签署日期不替代起始日期。'],
    ['身份证','识别正反面关键字段，要求在同一页或同一张图片。照片、打码及裁切情况仍需人工复核。'],
    ['社保缴纳记录','查询区间起始月份必须为 2025 年 1 月。不检查首次参保日期，不要求该月已有缴费，未设置查询截止月份。'],
    ['无房产证明','所有权／使用权、抵押、查封及行政限制等三个指定栏目，对应结果均为“无”。逐栏目匹配，不统计“无”字数量。'],
    ['学历学位证明','学历证书、学位证书、学历验证报告、学位验证报告四项齐全。学籍验证报告不可替代；明确的毕业年份须为 2026 年。'],
    ['完整性与身份','可识别页码时检查缺页。身份一致、未打码、未裁切及原件完整性由 HR 确认。未接入官方验真。'],
    ['结果处理','明确不符合自动退回；低置信度、缺少可靠定位或无法识别时转人工。不由 OCR 输出直接判定最终资格。']
  ];
  shell(`<div class="page-heading"><div><h1>企业预审规则</h1><p>2026.10.09 / v1 · 当前配置</p></div><span class="badge">只读</span></div><div class="rules-list">${rows.map(([t,p])=>`<div><h3>${t}</h3><p>${p}</p></div>`).join('')}</div>`);
}
function messages(){
  shell(`<div class="page-heading"><div><h1>消息记录</h1><p>申请状态更新</p></div></div>${state.list.length?state.list.map(a=>`<article class="event-row"><div><h3>${esc(a.applicant)} · ${statuses[a.status]}</h3><p>${esc(a.id)} · ${date(a.updated)}</p></div><button class="text-btn" data-action="detail" data-id="${a.id}">查看申请${icon('arrow-up-right')}</button></article>`).join(''):`<div class="empty">${icon('bell')}<h2>暂无消息</h2></div>`}`);
}
async function navigate(page){
  clearTimeout(state.timer);
  state.page=page;
  if(page==='new'){form();return;}
  if(page==='rules'){rules();return;}
  state.list=await api('/api/applications');
  if(page==='messages')messages();else list();
}
async function showDetail(id){clearTimeout(state.timer);state.current=await api(`/api/applications/${id}`);state.page='detail';detail();}
function showPreview(fileId,page=1){
  const app=state.current;
  const doc=app.documents.find(d=>d.id===fileId);
  const info=doc.pages[page-1];
  if(!info){toast('预览尚未生成。');return;}
  modal.className='preview-dialog';
  modal.innerHTML=`<div class="modal-head"><h2>材料与识别依据</h2><button class="btn icon" data-action="close-modal" aria-label="关闭预览">${icon('x')}</button></div><div class="preview-controls"><select id="preview-file" aria-label="选择材料">${app.documents.filter(d=>d.pages.length).map(d=>`<option value="${d.id}" ${d.id===fileId?'selected':''}>${esc(d.name)}</option>`).join('')}</select><span><button class="btn icon" data-action="preview-page" data-file="${fileId}" data-page="${page-1}" ${page===1?'disabled':''} aria-label="上一页">${icon('chevron-left')}</button>${page} / ${doc.pages.length}<button class="btn icon" data-action="preview-page" data-file="${fileId}" data-page="${page+1}" ${page===doc.pages.length?'disabled':''} aria-label="下一页">${icon('chevron-right')}</button></span></div><div class="preview-image"><img src="/api/applications/${app.id}/preview/${fileId}/${page}" alt="${esc(doc.name)} 第 ${page} 页原件"></div><details><summary class="preview-controls">${info.source==='pdf-text'?'PDF 文字层':'本地 OCR'} · ${info.reliable?'达到自动检查阈值':'需人工确认'} · 查看识别文本</summary><pre class="preview-text">${esc(info.text||'未识别到文字')}</pre></details>`;
  if(!modal.open)modal.showModal();icons();
}
function showDecision(status,appeal=false){
  modal.className='';
  const title=appeal?'申请人工复核':status==='approved'?'确认企业预审通过':'退回补正';
  modal.innerHTML=`<div class="modal-head"><h2>${title}</h2><button class="btn icon" data-action="close-modal" aria-label="关闭">${icon('x')}</button></div><form id="decision-form" class="modal-body" data-status="${status||''}" data-appeal="${appeal}"><label class="field"><span>${appeal?'复核说明':'复核依据 / 补正要求'}</span><textarea name="reason" required minlength="3" maxlength="2000" placeholder="${appeal?'请说明需要复核的问题':'请填写具体依据，不少于 3 个字'}"></textarea></label>${status==='approved'?'<label class="small"><input type="checkbox" required> 已核对申请人身份、完整未打码原件及相关审核依据</label>':''}<p class="error" id="decision-error" hidden></p><div class="modal-actions"><button type="button" class="btn" data-action="close-modal">取消</button><button type="submit" class="btn primary">确认${appeal?'提交':''}</button></div></form>`;
  modal.showModal();icons();
}
function readFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(new Error('文件读取失败'));r.readAsDataURL(file);});}
async function submitApplication(){
  if(state.submitting)return;
  if(Object.keys(slots).some(s=>!chosen(s).length)){toast('请选齐全部必需材料。');return;}
  state.applicant=root.querySelector('#applicant').value.trim();
  state.submitting=true;form();
  try{
    const items=[];
    for(const slot of Object.keys(slots)){
      for(const item of chosen(slot)){
        items.push(item.ref?{slot,ref:item.ref}:{slot,name:item.name,data:await readFile(item.file)});
      }
    }
    const app=await api('/api/applications',{method:'POST',body:JSON.stringify({applicant:state.applicant,items,previous:state.previous})});
    state.files={};state.previous=null;state.applicant='';state.sample=false;
    await showDetail(app.id);toast('整套材料已提交，正在进行本地预审。');
  }catch(e){toast(e.message);state.submitting=false;if(state.user)form();}
  finally{state.submitting=false;}
}
document.addEventListener('submit',async e=>{
  if(e.target.id==='login-form'){
    e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;
    const fields=new FormData(e.target);
    try{state.user=await api('/api/login',{method:'POST',body:JSON.stringify({username:fields.get('username'),password:fields.get('password'),role:state.role})});await navigate(state.user.role==='hr'?'list':'new');}
    catch(err){const p=document.getElementById('login-error');if(p){p.textContent=err.message;p.hidden=false;}else toast(err.message);}
    finally{button.disabled=false;}
  }
  if(e.target.id==='application-form'){e.preventDefault();await submitApplication();}
  if(e.target.id==='decision-form'){
    e.preventDefault();const formEl=e.target, button=formEl.querySelector('[type=submit]');button.disabled=true;
    const appeal=formEl.dataset.appeal==='true';
    try{
      state.current=await api(`/api/applications/${state.current.id}/${appeal?'appeal':'decision'}`,{method:'POST',body:JSON.stringify({status:formEl.dataset.status,reason:new FormData(formEl).get('reason')})});
      modal.close();detail();toast('处理结果已保存。');
    }catch(err){const p=document.getElementById('decision-error');p.textContent=err.message;p.hidden=false;}
    finally{button.disabled=false;}
  }
});
document.addEventListener('input',e=>{
  if(e.target.id==='applicant')state.applicant=e.target.value;
  if(e.target.id==='search'){state.search=e.target.value;document.getElementById('list-table').innerHTML=tableRows();icons();}
});
document.addEventListener('change',e=>{
  if(e.target.classList.contains('file-picker')){
    const slot=e.target.dataset.slot;
    const selected=[...e.target.files];
    for(const file of selected){
      if(!/\.(pdf|jpe?g|png)$/i.test(file.name)||!file.size||file.size>15*1024*1024){toast('仅支持非空 PDF/JPG/PNG，单文件不超过 15 MB。');continue;}
      const current=chosen(slot);
      if(!current.some(f=>f.name===file.name&&f.size===file.size))state.files[slot]=[...current,{name:file.name,size:file.size,file}];
    }
    state.sample=false;form();
  }
  if(e.target.id==='preview-file')showPreview(e.target.value);
});
document.addEventListener('click',async e=>{
  const button=e.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action;
  try{
    if(action==='role'){state.role=button.dataset.role;renderLogin();}
    if(action==='fill-login'){root.querySelector('[name=username]').value=state.role==='hr'?'hr':'employee';root.querySelector('[name=password]').value=state.role==='hr'?'Hr2026!':'Employee2026!';}
    if(action==='password'){const input=root.querySelector('[name=password]');input.type=input.type==='password'?'text':'password';button.setAttribute('aria-label',input.type==='password'?'显示密码':'隐藏密码');}
    if(action==='logout'){await api('/api/logout',{method:'POST',body:'{}'});state.user=null;state.files={};state.applicant='';state.previous=null;state.current=null;state.list=[];state.sample=false;clearTimeout(state.timer);renderLogin();}
    if(action==='nav'){await navigate(button.dataset.page);}
    if(action==='refresh'){await navigate('list');}
    if(action==='filter'){state.filter=button.dataset.value;list();}
    if(action==='remove-file'){state.files[button.dataset.slot].splice(Number(button.dataset.index),1);form();}
    if(action==='detail'){await showDetail(button.dataset.id);}
    if(action==='check-group'){checkGroup(button.dataset.status);}
    if(action==='back-detail'){state.page='detail';detail();}
    if(action==='close-modal'){modal.close();}
    if(action==='preview'){showPreview(button.dataset.file);}
    if(action==='preview-page'){showPreview(button.dataset.file,Number(button.dataset.page));}
    if(action==='evidence'){const proof=state.current.checks[Number(button.dataset.index)].evidence[0];showPreview(proof.file_id,proof.page);}
    if(action==='decision'){showDecision(button.dataset.status);}
    if(action==='appeal'){showDecision(null,true);}
    if(action==='correct'){
      const a=state.current;
      state.previous=a.id;state.applicant=a.applicant;state.files={};state.sample=false;
      for(const doc of a.documents){for(const slot of doc.slots){(state.files[slot]??=[]).push({name:doc.name,size:doc.size,ref:doc.id});}}
      state.page='new';form();
    }
    if(action==='samples'){
      if(Object.values(state.files).some(files=>files.length)&&!confirm('测试材料将替换当前尚未提交的文件选择，是否继续？'))return;
      button.disabled=true;
      const samples=await api('/api/samples');
      state.files={};state.previous=null;state.applicant='测试申请人';state.sample=true;
      for(const s of samples){
        const bytes=Uint8Array.from(atob(s.data),c=>c.charCodeAt(0));
        const file=new File([bytes],s.name,{type:'application/pdf'});
        state.files[s.slot]=[{file,name:s.name,size:file.size}];
      }
      state.page='new';form();toast('已载入虚构测试材料，点击“上传并预审”后才会提交。');
    }
  }catch(err){toast(err.message);if(button.isConnected)button.disabled=false;}
});
window.addEventListener('beforeunload',e=>{if(state.submitting){e.preventDefault();e.returnValue='';}});
(async()=>{try{const me=await api('/api/me');state.user=me.user;await navigate(state.user.role==='hr'?'list':'new');}catch{renderLogin();}})();
