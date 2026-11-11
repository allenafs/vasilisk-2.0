# -*- coding: utf-8 -*-
"""Локальная веб-панель http://127.0.0.1:9001/ui : статус, советы, вопросы ИИ, драфт, роль, проверка GSI."""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

import extras
import winmodel

PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>ВАСИЛИСК 2.0</title>
<style>
body{background:#14161a;color:#e6e6e6;font:14px system-ui,sans-serif;margin:0 auto;padding:16px;max-width:900px}
h2{margin:14px 0 8px;color:#f0b84a;font-size:15px}.card{background:#1d2026;border-radius:8px;padding:12px;margin-bottom:12px}
.item{display:inline-block;background:#2a2e36;border-radius:4px;padding:4px 8px;margin:2px}.good{color:#7bdc8a}.bad{color:#ff7b7b}
select,button,input{background:#2a2e36;color:#eee;border:1px solid #444;padding:6px;border-radius:4px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.err{color:#ffb86b;font-size:13px}
.a3{border-left:4px solid #ff5c5c}.a2{border-left:4px solid #ffd24a}.a1{border-left:4px solid #9fd6ff}.line{padding:6px 10px;margin:4px 0;background:#232730;border-radius:4px}
</style></head><body>
<div class="bar"><button onclick="tab('live')">В игре</button><button onclick="tab('draft')">Драфт</button>
 <label>Роль <select id="role" onchange="save()"><option value="">авто</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label>
 <label><input type="checkbox" id="voice" onchange="save()"> Голос</label>
 <label><input type="checkbox" id="llm" onchange="save()"> ИИ (Ollama)</label>
 <label><input type="checkbox" id="coach" onchange="save()"> ИИ-подсказки сами</label></div>
<div id="stat" class="err"></div>
<div id="live"><div class="card"><input id="q" size="52" placeholder="Спроси ИИ: что мне купить? как играть против...?" onkeydown="if(event.key=='Enter')ask()"> <button onclick="ask()">Спросить</button><div id="ans" style="margin-top:8px"></div></div>
<div class="card"><b id="head">Жду матч…</b><div id="advice"></div></div></div>
<div id="draft" style="display:none"><div class="card"><b>Враги (до 5):</b><div id="en"></div><b>Союзники (до 4):</b><div id="al"></div><button onclick="go()">Анализ драфта</button></div><div id="dres" class="card"></div></div>
<script>
const $=id=>document.getElementById(id);let cfgSet=false;
const pct=x=>(x*100).toFixed(1)+'%';
function tab(x){$('live').style.display=x=='live'?'':'none';$('draft').style.display=x=='draft'?'':'none'}
const post=(u,b)=>fetch(u,{method:'POST',body:JSON.stringify(b)}).then(r=>r.json());
function save(){post('/api/settings',{role:$('role').value,voice:$('voice').checked,llm:$('llm').checked,coach:$('coach').checked})}
function ask(){const q=$('q').value.trim();if(!q)return;$('ans').textContent='Думаю…';post('/api/ask',{q}).then(r=>$('ans').textContent=r.answer)}
async function tick(){try{const a=await (await fetch('/api/live')).json();
 if(!cfgSet){$('role').value=a.settings.role_num;$('voice').checked=a.settings.voice;$('llm').checked=a.settings.llm;$('coach').checked=a.settings.coach;cfgSet=true}
 $('stat').textContent=a.status_line;
 $('head').textContent=a.hero?`${a.hero} · ${a.clock} · золото ${a.gold}`+(a.winprob!=null?` · шанс по драфту ${pct(a.winprob)}`:''):'Жду матч…';
 $('advice').innerHTML=a.advice.slice().reverse().map(x=>`<div class="line a${x.prio}">[${x.clock}] ${x.text}</div>`).join('')}catch(e){$('stat').textContent='Нет связи с тренером: '+e}}
async function init(){const H=await (await fetch('/api/heroes')).json();
 for(const [id,n] of [['en',5],['al',4]]){$(id).innerHTML=Array.from({length:n},()=>`<select class="${id}"><option value="">—</option>${H.map(h=>`<option value="${h.npc}">${h.name}</option>`).join('')}</select> `).join('')}}
async function go(){const v=c=>[...document.querySelectorAll('.'+c)].map(s=>s.value).filter(Boolean);
 const r=await post('/api/draft',{enemies:v('en'),allies:v('al')});
 let h=r.winprob!=null?`<b>Шанс победы по драфту: ${pct(r.winprob)}</b><br>`:'';
 h+='<h2>Лучшие пики против врагов</h2>'+r.picks.map(x=>`<span class="item good">${x.name} ${pct(x.model!=null?x.model:x.wr)}</span>`).join('');
 if(r.counter.length)h+='<h2>Контр-предметы</h2>'+r.counter.map(i=>`<div><b>${i.item}</b>: ${i.why}</div>`).join('');
 $('dres').innerHTML=h}
init();tick();setInterval(tick,2000);
</script></body></html>"""

ROLE_NUM = {"carry": "1", "mid": "2", "offlane": "3", "pos4": "4", "support": "5"}


def register(app: web.Application, coach, cfg: dict, save_cfg, builds, port: int):
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    @web.middleware
    async def origin_guard(request, handler):          # чужие сайты не смогут слать команды из браузера
        if request.path.startswith(("/ui", "/api/")) and request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return web.json_response({"error": "forbidden host"}, status=403)
        if request.method == "POST" and request.path.startswith("/api/"):
            o = request.headers.get("Origin")
            if o and o not in allowed:
                return web.json_response({"error": "forbidden origin"}, status=403)
        return await handler(request)

    app.middlewares.append(origin_guard)
    adv = coach.advisor

    async def page(_): return web.Response(text=PAGE, content_type="text/html")

    async def heroes(_):
        hs = [{"npc": k, "name": v.get("localized_name", k)} for k, v in builds.meta.items()]
        return web.json_response(sorted(hs, key=lambda h: h["name"]))

    async def live(_):
        st = coach.state
        fresh = st.payloads and time.time() - st.last_payload_ts < 10
        blocks = coach.blocks_report()
        status = (f"LLM: {'✓ ' + coach.llm.model if coach.llm.available else 'недоступна (шаблоны)'} · "
                  f"модель драфта: {'✓' if winmodel.load() else 'не обучена'} · {blocks}")
        meta = builds.meta
        wp = extras.win_probability(meta, adv.extra.allies, adv.extra.enemies) if adv.extra.enemies else None
        return web.json_response({
            "hero": (st.hero_key or "").replace("npc_dota_hero_", "").replace("_", " ").title() if fresh else None,
            "clock": st.fmt_clock(), "gold": int(st.gold), "winprob": wp, "advice": coach.advice_log[-15:],
            "status_line": status,
            "settings": {"role_num": ROLE_NUM.get(adv.role, ""), "voice": coach.speaker.enabled,
                         "llm": coach.llm.enabled, "coach": coach.free_coach}})

    async def ask(request):
        q = str((await request.json()).get("q", ""))[:500]
        ans = await coach.llm.ask(q, extras.build_context(coach.state, adv))
        return web.json_response({"answer": ans})

    async def draft(request):
        d = await request.json()
        enemies = [e for e in d.get("enemies", []) if e in builds.meta][:5]
        allies = [a for a in d.get("allies", []) if a in builds.meta][:4]
        adv.extra.set_draft(enemies, allies)
        adv.extra._counter_said.clear()
        recs = [builds.meta[e] for e in enemies]
        return web.json_response({"picks": extras.draft_picks(builds.meta, enemies, allies),
                                  "winprob": extras.win_probability(builds.meta, allies, enemies) if enemies else None,
                                  "counter": extras.counter_items(recs)})

    async def settings(request):
        d = await request.json()
        if "role" in d:
            role = extras.normalize_role(d["role"]) if d["role"] else "carry"
            if role != adv.role:
                adv.role, cfg["role"], adv.plan = role, role, []     # план сборки перезагрузится под роль
        if "voice" in d: coach.speaker.enabled = cfg["voice"] = bool(d["voice"])
        if "llm" in d: coach.llm.enabled = cfg["llm"] = bool(d["llm"])
        if "coach" in d: coach.free_coach = cfg["free_coach"] = bool(d["coach"])
        if coach.llm.enabled and not coach.llm.available:
            await coach.llm.check()
        save_cfg()
        return web.json_response({"ok": True})

    async def blocks(_):
        return web.json_response({"blocks": sorted(coach.blocks_seen), "report": coach.blocks_report()})

    app.router.add_get("/ui", page)
    app.router.add_get("/api/heroes", heroes)
    app.router.add_get("/api/live", live)
    app.router.add_get("/api/blocks", blocks)
    app.router.add_post("/api/ask", ask)
    app.router.add_post("/api/draft", draft)
    app.router.add_post("/api/settings", settings)
