'use strict';
const {app,BrowserWindow,Menu,shell,dialog,session}=require('electron');
const HOME='https://osamababeker4-netizen.github.io/asas-lims/?release=8-1-0';
const trusted=url=>{try{const u=new URL(url);return u.origin==='https://osamababeker4-netizen.github.io'&&u.pathname.startsWith('/asas-lims/');}catch{return false;}};
function external(url){try{if(['https:','mailto:','tel:'].includes(new URL(url).protocol))shell.openExternal(url);}catch{}}
let main;
app.setName('ASAS LIMS');
if(!app.requestSingleInstanceLock())app.quit();
else {
app.on('second-instance',()=>{if(main){if(main.isMinimized())main.restore();main.focus();}});
app.whenReady().then(()=>{
 session.defaultSession.setPermissionRequestHandler((webContents,permission,callback)=>{
  if(!trusted(webContents.getURL())||permission!=='geolocation')return callback(false);
  dialog.showMessageBox(main,{type:'question',message:'Allow ASAS LIMS to use your location? / السماح باستخدام موقعك؟',buttons:['Allow / سماح','Deny / رفض'],defaultId:1,cancelId:1}).then(result=>callback(result.response===0));
 });
 session.defaultSession.setPermissionCheckHandler((wc,permission,origin)=>permission==='geolocation'&&origin==='https://osamababeker4-netizen.github.io');
 main=new BrowserWindow({width:1380,height:900,minWidth:720,minHeight:520,title:'ASAS LIMS 8.1.0',webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
 main.webContents.on('will-navigate',(event,url)=>{if(!trusted(url)){event.preventDefault();external(url);}});
 main.webContents.setWindowOpenHandler(({url})=>{external(url);return {action:'deny'};});
 main.webContents.on('did-fail-load',(_event,code,_description,_url,isMain)=>{if(isMain&&code!==-3)dialog.showMessageBox(main,{type:'error',message:'Check your internet connection, then use Reload. / تحقق من الاتصال ثم أعد التحميل.'});});
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'ASAS LIMS',submenu:[{label:'Home / الرئيسية',click:()=>main.loadURL(HOME)},{label:'Reload / تحديث',accelerator:'CmdOrCtrl+R',click:()=>main.webContents.reloadIgnoringCache()},{label:'Print / طباعة',accelerator:'CmdOrCtrl+P',click:()=>main.webContents.print()},{type:'separator'},{role:'quit'}]},{label:'Edit',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},{label:'View',submenu:[{role:'zoomIn'},{role:'zoomOut'},{role:'resetZoom'},{role:'togglefullscreen'}]}]));
 main.loadURL(HOME);
});
app.on('window-all-closed',()=>app.quit());
}
