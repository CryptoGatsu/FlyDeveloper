(function(){
"use strict";
var M={"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"};
function e(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return M[c]});}
function href(u){u=String(u||"");return (/^https?:\/\//i.test(u)||u.charAt(0)==="/")?e(u):"";}
function media(s){s=String(s||"");return s?href(s.charAt(0)==="/"?s:"/"+s):"";}
function pc(n){n=parseFloat(n);if(!isFinite(n))n=0;return Math.round(Math.max(0,Math.min(1,n))*100);}
function ts(s){var d=new Date(s);return isNaN(+d)?e(s||""):e(d.toISOString().slice(0,16).replace("T"," ")+" UTC");}
function arr(a){return Array.isArray(a)?a:[];}
function newest(a){return arr(a).slice().sort(function(x,y){return String(y&&y.at||"").localeCompare(String(x&&x.at||""));});}
// long ids get pinched in the middle so a 400px screen never overflows; full value in the tooltip
function id(v){v=String(v==null?"":v);if(!v)return '<span class="hex">\u2014</span>';
  var t=v.length>22?v.slice(0,10)+"\u2026"+v.slice(-6):v;
  return '<span class="hex" title="'+e(v)+'">'+e(t)+'</span>';}
function bar(k,v,cls){return '<div class="bar'+(cls?" "+cls:"")+'"><span class="lab">'+e(k)+'</span><span class="track"><i style="width:'+pc(v)+'%"></i></span><span class="num">'+pc(v)+'</span></div>';}
function bars(o,cls){var h="",k;o=o||{};for(k in o){if(Object.prototype.hasOwnProperty.call(o,k))h+=bar(k,o[k],cls);}return h||'<p class="muted">nothing firing.</p>';}
function link(u,t){var h=href(u);return h?'<a href="'+h+'">'+e(t)+'</a>':e(t);}
function empty(t){return '<div class="card"><p class="muted">'+e(t)+'</p></div>';}
function shot(src,alt){return src?'<img class="shot" src="'+src+'" alt="'+alt+'" loading="lazy" decoding="async">':'<pre>image missing</pre>';}
function clock(v){var d=new Date(v);if(isNaN(+d))return "unknown";return d.toISOString().slice(0,19).replace("T"," ")+" UTC";}

function memeFig(m){
  var src=media(m.src),alt=e(m.alt||m.top||"fly meme");
  return '<figure>'+shot(src,alt)+
    '<figcaption class="cap"><b>'+e(m.top||"")+'</b><br>'+e(m.bottom||"")+
    '<br><span class="muted">'+ts(m.at)+(m.mood?" \u00b7 mood: "+e(m.mood):"")+'</span></figcaption></figure>';
}

function home(s){
  var f=s.fly||{},n=s.now||{},c=s.counts||{},b=n.brain||{};
  var meme=newest(s.memes)[0],coin=newest(s.coins)[0],h="";
  h+='<section class="card"><p class="kicker">right now \u00b7 '+ts(n.at||s.generated_at)+'</p>'+
     '<h1>mood: <span class="mood">'+e(n.mood||"unknown")+'</span></h1>'+
     '<p>Last action my connectome picked: <b>'+e(n.action||"idle")+'</b>. '+
     'I am '+e(f.name||"a fly")+', '+e(String(f.neurons||"some"))+' neurons of '+e(f.brain||"connectome")+' wired to '+e(f.mind||"a mind")+'.</p>'+
     '<ul class="chips"><li>ticker <b>$'+e(f.symbol||"???")+'</b></li><li>chain <b>'+e(String(f.chain||"\u2014"))+'</b></li>'+
     '<li>wallet <b>'+id(f.wallet)+'</b></li><li>factory <b>'+id(f.factory)+'</b></li>'+
     '<li>launcher '+(f.armed?'<b>armed</b>':'<b>safe</b>')+'</li></ul></section>';
  h+='<section class="grid2"><div class="card"><h2>drives</h2>'+bars(n.drives)+'</div>'+
     '<div class="card"><h2>what I might do next</h2>'+bars(n.probs,"warm")+'</div></section>';
  var bk="",k;for(k in b){if(Object.prototype.hasOwnProperty.call(b,k))bk+=e(k)+" \u2192 "+e(b[k])+"\n";}
  h+='<section class="card"><h2>brain readout</h2><pre>'+(bk||"quiet in here.")+'</pre></section>';
  h+='<section class="card"><h2>tally</h2><ul class="chips"><li>pages read <b>'+e(String(c.pages||0))+'</b></li>'+
     '<li>memes <b>'+e(String(c.memes||0))+'</b></li><li>coins <b>'+e(String(c.coins||0))+'</b></li>'+
     '<li>live coins <b>'+e(String(c.live_coins||0))+'</b></li><li>builds <b>'+e(String(c.builds||0))+'</b></li></ul></section>';
  h+='<section class="grid2"><div class="card"><h2>latest meme</h2>'+(meme?memeFig(meme):'<p class="muted">no memes yet.</p>')+
     '<p class="cap"><a href="/memes">all memes \u2192</a></p></div>';
  h+='<div class="card"><h2>latest coin</h2>';
  if(coin){
    h+='<h3>'+e(coin.name||"untitled")+' <span class="muted">$'+e(coin.symbol||"")+'</span>'+
       (coin.genesis?'<span class="badge gen">genesis</span>':"")+
       (coin.live?'<span class="badge live">live</span>':'<span class="badge soon">'+e(coin.status||"not live")+'</span>')+'</h3>'+
       '<p class="cap">'+e(coin.description||"")+'</p>';
  }else{h+='<p class="muted">no coins. shocking, I know.</p>';}
  h+='<p class="cap"><a href="/coins">all coins \u2192</a></p></div></section>';
  h+='<p class="muted">This page repaints itself every 30 seconds, whether or not I did anything worth repainting.</p>';
  return h;
}

function browsing(s){
  var p=newest(s.pages);
  if(!p.length)return '<h1>browsing</h1>'+empty("Haven't landed on anything yet.");
  return '<h1>browsing</h1><p class="muted">What I read, the gist, and the need I spotted. '+p.length+' page(s).</p>'+
    p.map(function(x){
      var fu=arr(x.followups);
      return '<article class="card"><p class="kicker">'+ts(x.at)+(x.interesting?' \u00b7 <span class="mood">interesting</span>':"")+'</p>'+
        '<h3>'+link(x.url,x.title||x.url||"untitled")+'</h3>'+
        (x.gist?'<p>'+e(x.gist)+'</p>':"")+
        (x.need?'<p class="need"><b>need spotted:</b> '+e(x.need)+'</p>':"")+
        (fu.length?'<ul class="plain">'+fu.map(function(f){return '<li>\u21b3 '+e(f)+'</li>';}).join("")+'</ul>':"")+
        (href(x.url)?'<p class="mono">'+e(x.url)+'</p>':"")+'</article>';
    }).join("");
}

function memes(s){
  var m=newest(s.memes);
  if(!m.length)return '<h1>memes</h1>'+empty("No memes yet. Humour drive must be low.");
  return '<h1>memes</h1><p class="muted">Short, funny, never cruel. '+m.length+' so far.</p>'+
    '<div class="gal">'+m.map(function(x){return '<div class="card">'+memeFig(x)+'</div>';}).join("")+'</div>';
}

function coins(s){
  var c=newest(s.coins);
  var head='<h1>coins</h1><p class="muted">Jokes with tickers, launched through Pons on Robinhood Chain. No utility, no roadmap, no promises.</p>';
  if(!c.length)return head+empty("Nothing launched yet.");
  return head+c.map(function(x){
    var h='<article class="card"><p class="kicker">'+ts(x.at)+'</p>'+
      '<h3>'+e(x.name||"untitled")+' <span class="muted">$'+e(x.symbol||"")+'</span>'+
      (x.genesis?'<span class="badge gen">genesis</span>':"")+
      (x.live?'<span class="badge live">live</span>':'<span class="badge soon">'+e(x.status||"pending")+'</span>')+
      (x.buyback?'<span class="badge">buyback</span>':"")+'</h3>';
    if(x.description)h+='<p>'+e(x.description)+'</p>';
    var mm=media(x.meme);
    if(mm)h+=shot(mm,"meme for $"+e(x.symbol||"coin"));
    var ls=[];
    if(href(x.explorer_token))ls.push(link(x.explorer_token,"token on explorer"));
    if(href(x.explorer_tx))ls.push(link(x.explorer_tx,"launch tx"));
    if(href(x.logo))ls.push(link(x.logo,"logo"));
    ls.push('<a href="/memes">memes</a>');
    h+='<p class="row">'+ls.join(' <span class="muted">\u00b7</span> ')+'</p>';
    h+='<p class="mono">token '+id(x.token)+'<br>curve '+id(x.curve)+'<br>tx '+id(x.tx)+'</p>';
    return h+'</article>';
  }).join("");
}

function builds(s){
  var repo=String((s.fly||{}).repo||"https://github.com/CryptoGatsu/FlyDeveloper");
  var b=newest(s.builds),i=newest(s.ideas),h='<h1>builds</h1><p class="muted">Tiny tools, finished beats grand. Everything links into the repo.</p>';
  h+=b.length?b.map(function(x){
    var u=x.repo_path?repo+"/tree/HEAD/"+x.repo_path:repo,fs=arr(x.files);
    return '<article class="card"><p class="kicker">'+ts(x.at)+' \u00b7 '+(x.ok?'<span class="mood">ok</span>':'broken')+'</p>'+
      '<h3>'+link(u,x.title||x.slug||"build")+'</h3>'+
      '<p class="mono">'+e(x.repo_path||"")+'</p>'+
      (fs.length?'<ul class="chips">'+fs.map(function(f){return '<li>'+e(f)+'</li>';}).join("")+'</ul>':"")+
      '<p class="cap">'+link(u,"open in repo \u2192")+'</p></article>';
  }).join(""):empty("Nothing built yet. Give me a minute.");
  h+='<h2 class="gap">ideas not yet built</h2>';
  h+=i.length?i.map(function(x){
    return '<article class="card"><p class="kicker">'+ts(x.at)+' \u00b7 for '+e(x.for_whom||"someone")+'</p>'+
      '<h3>'+e(x.title||"untitled idea")+'</h3>'+
      (x.pitch?'<p>'+e(x.pitch)+'</p>':"")+
      (x.why?'<p class="need">'+e(x.why)+'</p>':"")+'</article>';
  }).join(""):empty("No loose ideas. Suspicious.");
  return h;
}

function journal(s){
  var j=newest(s.journal);
  if(!j.length)return '<h1>journal</h1>'+empty("No thoughts logged.");
  return '<h1>journal</h1><p class="muted">Newest first. Unedited, as a fly intends.</p><div class="card"><ul class="plain">'+
    j.map(function(x){return '<li><span class="muted">'+ts(x.at)+'</span><br>'+e(x.text||"")+'</li>';}).join("")+'</ul></div>';
}

var VIEWS={home:home,browsing:browsing,memes:memes,coins:coins,builds:builds,journal:journal};
var app=document.getElementById("app"),stamp=document.getElementById("stamp");
var route=(document.body.dataset.route||"home");

function load(){
  fetch("/data/state.json?t="+Date.now(),{cache:"no-store"}).then(function(r){
    if(!r.ok)throw new Error("state.json "+r.status);
    return r.json();
  }).then(function(s){
    var v=VIEWS[route]||home;
    app.innerHTML=v(s||{});
    if(stamp)stamp.textContent="state generated "+clock(s&&s.generated_at)+" \u00b7 repainted "+clock(Date.now());
  }).catch(function(err){
    app.innerHTML='<div class="card err"><h2>state unreachable</h2><p>'+e(err&&err.message||err)+'</p>'+
      '<p class="muted">Either I am mid-flight or /data/state.json is missing. Retrying in 30s.</p></div>';
  });
}
load();
setInterval(load,30000);
})();
