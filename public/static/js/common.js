// Shared UI helpers for Spotify Manager
(function(){
  'use strict';

  function makeToast(message, type='info', timeout=4000){
    const root = document.getElementById('toast-root');
    if(!root) return;
    const el = document.createElement('div');
    el.className = 'toast ' + (type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : 'toast-info');
    el.textContent = message;
    root.appendChild(el);
    requestAnimationFrame(()=> el.classList.add('visible'));
    setTimeout(()=>{ el.classList.remove('visible'); setTimeout(()=> el.remove(), 300); }, timeout);
    return el;
  }

  function quickHasFieldsToWork(form){
    try{
      const action = (form.getAttribute('action') || '').toLowerCase();
      if(action.includes('/merge') || form.classList.contains('merge')){
        const anyChecked = !!form.querySelector('input[type="checkbox"][name="playlist"]:checked');
        const nameEl = form.querySelector('[name="name"]');
        const nameVal = nameEl && nameEl.value && nameEl.value.trim();
        return anyChecked || !!nameVal;
      }
      if(action.includes('/clean') || form.classList.contains('clean-panel')){
        const hidden = form.querySelector('[name="clean_playlist"]');
        const nameEl = form.querySelector('[name="clean_playlist_name"]');
        const val = (hidden && hidden.value && hidden.value.trim()) || (nameEl && nameEl.value && nameEl.value.trim());
        return !!val;
      }
      if(action.includes('/update_liked') || form.querySelector('[name="liked_name"]')){
        const el = form.querySelector('[name="liked_name"]');
        return !!(el && el.value && el.value.trim());
      }
      const inputs = Array.from(form.querySelectorAll('input,textarea,select'));
      for(const inp of inputs){
        if(inp.type === 'checkbox' || inp.type === 'radio'){
          if(inp.checked) return true;
        } else if(inp.name && inp.value && String(inp.value).trim()){
          return true;
        }
      }
      return false;
    }catch(err){
      return true;
    }
  }

  function isGuardedForEmptySubmission(form){
    const action = (form.getAttribute('action') || '').toLowerCase();
    if(action.includes('/merge') || form.classList.contains('merge')) return true;
    if(action.includes('/clean') || form.classList.contains('clean-panel')) return true;
    return false;
  }

  function setButtonWorking(btn){
    try{
      if(!btn) return;
      if(btn.__working) return;
      btn.__working = true;
      btn.disabled = true;
      btn.classList.add('working');
      btn.setAttribute('aria-busy', 'true');
      if(!btn.querySelector('.spinner')){
        const sp = document.createElement('span');
        sp.className = 'spinner';
        sp.setAttribute('aria-hidden', 'true');
        btn.insertBefore(sp, btn.firstChild);
      }
    }catch(err){ console && console.error && console.error('setButtonWorking', err); }
  }

  function clearButtonWorking(btn){
    try{
      if(!btn) return;
      if(!btn.__working) return;
      btn.__working = false;
      btn.disabled = false;
      btn.classList.remove('working');
      btn.removeAttribute('aria-busy');
      const sp = btn.querySelector('.spinner'); if(sp) sp.remove();
    }catch(err){ console && console.error && console.error('clearButtonWorking', err); }
  }

  function setFormWorking(form){
    form.querySelectorAll('button[type=submit], button:not([type]), input[type=submit]').forEach(b => setButtonWorking(b));
  }

  function clearFormWorking(form){
    form.querySelectorAll('button[type=submit], button:not([type]), input[type=submit]').forEach(b => clearButtonWorking(b));
  }

  function initForms(){
    document.querySelectorAll('form').forEach(form => {
      if(form.classList.contains('ajax')){
        form.addEventListener('submit', async function(e){
          if(isGuardedForEmptySubmission(form) && !quickHasFieldsToWork(form)){
            e.preventDefault();
            e.stopImmediatePropagation();
            makeToast('Please select a playlist', 'info', 1500);
            return false;
          }

          e.preventDefault();
          setFormWorking(form);
          // If this is the Clean form, show a small percentage indicator
          let percEl = null;
          let percTimer = null;
          let percBtn = null;
          try{
            const action = (form.getAttribute('action') || '').toLowerCase();
            if(action.includes('/clean')){
              // find the primary button to attach percentage to
              percBtn = form.querySelector('button[type=submit], button:not([type])');
              if(percBtn){
                // create percentage element and insert after button
                percEl = document.createElement('span');
                percEl.className = 'ajax-perc';
                percEl.textContent = '0%';
                percBtn.insertAdjacentElement('afterend', percEl);

                // determine total songs to process from page-data if available
                let total = 100; // fallback
                try{
                  const pd = document.getElementById('page-data');
                  if(pd){
                    const pls = JSON.parse(pd.getAttribute('data-playlists') || '[]');
                    const hid = form.querySelector('[name="clean_playlist"]');
                    const pid = hid && hid.value ? hid.value : null;
                    if(pid){
                      const p = pls.find(x => x.id === pid);
                      if(p && p.tracks) total = Number(p.tracks) || total;
                    } else {
                      // try to match typed name (fallback to first playlist)
                      const nameEl = form.querySelector('[name="clean_playlist_name"]');
                      const typed = nameEl && nameEl.value ? nameEl.value.trim().toLowerCase() : '';
                      if(typed){
                        const p = pls.find(x => (x.name||'').toLowerCase().includes(typed));
                        if(p && p.tracks) total = Number(p.tracks) || total;
                      }
                    }
                  }
                }catch(err){ /* ignore parse errors */ }

                // animate percentage up to a soft cap while request is in-flight
                const targetCap = 95; // don't reach 100% until finished
                const duration = Math.min(30000, Math.max(1500, total * 60));
                const stepMs = 200;
                const steps = Math.max(3, Math.floor(duration / stepMs));
                let current = 0;
                const delta = targetCap / steps;
                percTimer = setInterval(()=>{
                  current = Math.min(targetCap, current + delta);
                  percEl.textContent = Math.floor(current) + '%';
                }, stepMs);
                // store on button so we can clear later if needed
                percBtn.__percTimer = percTimer;
                percBtn.__percEl = percEl;
              }
            }
          }catch(err){ console && console.error && console.error('initForms clean perc', err); }
          try{
            const formData = new FormData(form);
            const resp = await fetch(form.action, {
              method: form.method || 'POST',
              body: formData,
              credentials: 'same-origin',
              headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const text = await resp.text();
            // Prefer JSON responses for AJAX flows. If JSON contains a
            // background task id, poll the server for progress updates and
            // update the percentage element in the page.
            let handled = false;
            try{
              const j = JSON.parse(text);
              if(j){
                // If server returned a task id, poll progress endpoint.
                if(j.task_id){
                  handled = true;
                  const taskId = j.task_id;
                  // If a simulated perc timer was running, stop it — we'll drive
                  // the percentage from the server polling instead.
                  try{
                    if(percBtn && percBtn.__percTimer){ clearInterval(percBtn.__percTimer); delete percBtn.__percTimer; }
                  }catch(e){}
                  const poll = async ()=>{
                    try{
                      const r = await fetch(`/clean_progress/${taskId}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' }});
                      if(!r.ok){
                        const t = await r.text();
                        makeToast('Progress check failed', 'error', 3000);
                        return;
                      }
                      const p = await r.json();
                      if(!p || !p.ok){
                        makeToast(p && p.error ? p.error : 'Progress error', 'error', 3000);
                        return;
                      }
                      const processed = Number(p.processed || 0);
                      const total = Number(p.total || 0);
                      if(percEl){
                        let percent = 0;
                        if(total > 0) percent = Math.floor((processed/total)*100);
                        else if(p.status === 'running') percent = 50;
                        else if(p.status === 'done') percent = 100;
                        percEl.textContent = Math.min(100, Math.max(0, percent)) + '%';
                      }
                      if(p.status === 'done'){
                        if(percBtn && percBtn.__percEl){
                          const el = percBtn.__percEl;
                          el.textContent = '100%';
                          setTimeout(()=>{ el.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }, 700);
                        }
                        makeToast(p.message || 'Clean finished', 'success', 4000);
                        return;
                      }
                      if(p.status === 'error'){
                        makeToast(p.message || 'Clean failed', 'error', 5000);
                        if(percBtn && percBtn.__percEl){
                          try{ percBtn.__percEl.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }catch(e){}
                        }
                        return;
                      }
                      // still running: poll again shortly
                      setTimeout(poll, 900);
                    }catch(err){
                      console && console.error && console.error('poll progress', err);
                      setTimeout(poll, 1500);
                    }
                  };
                  // start polling
                  setTimeout(poll, 500);
                } else if(j.message || j.msg){
                  const m = j.message || j.msg;
                  const t = (j.ok === false) ? 'error' : 'success';
                  makeToast(m, t, 4000);
                  handled = true;
                }
              }
            }catch(err){ /* not JSON */ }

            if(!handled){
              const parser = new DOMParser();
              const doc = parser.parseFromString(text, 'text/html');
              const flashEl = doc.querySelector('#flashes .flash');
              if(flashEl){
                const cls = flashEl.className || '';
                const type = cls.includes('success') ? 'success' : cls.includes('error') ? 'error' : 'info';
                makeToast(flashEl.textContent.trim(), type, 4000);
              } else if(resp.ok){
                makeToast('Done', 'success', 3000);
              } else {
                makeToast('Request failed', 'error', 4000);
              }
            }
          }catch(err){
            console && console.error && console.error(err);
            makeToast('Request failed', 'error', 4000);
          }finally{
            // complete and clear percentage indicator if present
            try{
              if(percTimer) clearInterval(percTimer);
              if(percBtn && percBtn.__percEl){
                const el = percBtn.__percEl;
                el.textContent = '100%';
                setTimeout(()=>{ el.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }, 700);
              }
            }catch(err){/* ignore */}
            clearFormWorking(form);
          }
        });
      } else {
        form.addEventListener('submit', function(e){
          if(isGuardedForEmptySubmission(form) && !quickHasFieldsToWork(form)){
            e.preventDefault();
            e.stopImmediatePropagation();
            makeToast('Please select a playlist', 'info', 1500);
            return false;
          }

          setFormWorking(form);
        });
      }
    });
  }

  function initFlashes(){
    const list = document.getElementById('flashes');
    if(list){
      Array.from(list.querySelectorAll('.flash')).forEach(li => {
        const cls = li.className || '';
        const type = cls.includes('success') ? 'success' : cls.includes('error') ? 'error' : 'info';
        makeToast(li.textContent.trim(), type);
      });
    }
  }

  function initUserMenu(){
    const userInfo = document.querySelector('.header .user-info');
    const trigger = document.querySelector('.header .user-info .account-trigger');
    if(userInfo){
      if(trigger){
        trigger.addEventListener('click', function(e){
          if(e.target && (e.target.tagName === 'BUTTON' || e.target.closest('form'))) return;
          userInfo.classList.toggle('open');
        });
      }

      document.addEventListener('click', function(e){
        if(!userInfo.contains(e.target)) userInfo.classList.remove('open');
      });

      document.addEventListener('keydown', function(e){ if(e.key === 'Escape') userInfo.classList.remove('open'); });
    }
  }

  // Expose a small API
  window.UI = window.UI || {};
  window.UI.makeToast = makeToast;
  window.UI.setButtonWorking = setButtonWorking;
  window.UI.clearButtonWorking = clearButtonWorking;
  window.UI.setFormWorking = setFormWorking;
  window.UI.clearFormWorking = clearFormWorking;

  document.addEventListener('DOMContentLoaded', function(){
    initFlashes();
    initForms();
    initUserMenu();
  });

})();
