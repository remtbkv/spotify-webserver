// Page-specific JS for the Playlists view
(function(){
  'use strict';

  function togglePanel(btn){
    const head = btn.parentElement;
    const body = head.nextElementSibling;
    if(!body) return;
    const isCollapsed = body.classList.contains('collapsed');
    const closedText = btn.getAttribute('data-closed-text') || 'Show';
    const openText = btn.getAttribute('data-open-text') || 'Hide';

    if(isCollapsed){
      body.classList.remove('collapsed');
      body.style.overflow = 'hidden';
      const height = body.scrollHeight;
      body.style.maxHeight = '0';
      body.offsetHeight;
      body.style.maxHeight = height + 'px';
      btn.textContent = openText;
      btn.setAttribute('aria-expanded', 'true');

      const onEnd = function(e){
        if(e.propertyName === 'max-height'){
          body.style.maxHeight = '';
          body.style.overflow = '';
          body.removeEventListener('transitionend', onEnd);
        }
      };
      body.addEventListener('transitionend', onEnd);
    } else {
      const height = body.scrollHeight;
      body.style.maxHeight = height + 'px';
      body.style.overflow = 'hidden';
      body.offsetHeight;
      body.style.maxHeight = '0';
      btn.textContent = closedText;
      btn.setAttribute('aria-expanded', 'false');

      const onEndClose = function(e){
        if(e.propertyName === 'max-height'){
          body.classList.add('collapsed');
          body.style.maxHeight = '';
          body.style.overflow = '';
          body.removeEventListener('transitionend', onEndClose);
        }
      };
      body.addEventListener('transitionend', onEndClose);
    }
  }

  function toggleDetails(el){
    const targetId = el.getAttribute('aria-controls');
    if(!targetId) return;
    const details = document.getElementById(targetId);
    if(!details) return;
    const isCollapsed = details.classList.contains('collapsed');
    const closedText = el.getAttribute('data-closed-text') || 'Show';
    const openText = el.getAttribute('data-open-text') || 'Hide';

    if(isCollapsed){
      details.classList.remove('collapsed');
      details.style.overflow = 'hidden';
      const height = details.scrollHeight;
      details.style.maxHeight = '0';
      details.offsetHeight;
      details.style.maxHeight = height + 'px';
      el.textContent = openText;
      el.setAttribute('aria-expanded', 'true');
      details.setAttribute('aria-hidden', 'false');

      const onEnd = function(e){
        if(e.propertyName === 'max-height'){
          details.style.maxHeight = '';
          details.style.overflow = '';
          details.removeEventListener('transitionend', onEnd);
        }
      };
      details.addEventListener('transitionend', onEnd);
    } else {
      const height = details.scrollHeight;
      details.style.maxHeight = height + 'px';
      details.offsetHeight;
      details.style.overflow = 'hidden';
      details.style.maxHeight = '0';
      el.textContent = closedText;
      el.setAttribute('aria-expanded', 'false');
      details.setAttribute('aria-hidden', 'true');

      const onEndClose = function(e){
        if(e.propertyName === 'max-height'){
          details.classList.add('collapsed');
          details.style.maxHeight = '';
          details.style.overflow = '';
          details.removeEventListener('transitionend', onEndClose);
        }
      };
      details.addEventListener('transitionend', onEndClose);
    }

    const wrapper = el.closest('.inline-toggle-wrapper');
    if(wrapper) wrapper.classList.toggle('open', !isCollapsed);
    if(el.classList && el.classList.contains('toggle-panel')){
      el.classList.toggle('open', !isCollapsed);
    }
  }

  function initTypeahead(){
    const input = document.getElementById('clean_playlist_name');
    const hidden = document.getElementById('clean_playlist');
    const box = document.getElementById('suggestions');
    if(!input || !box) return;
    const items = Array.from(box.querySelectorAll('.typeahead-item'));

    // Make items keyboard-focusable
    items.forEach(it => { try{ it.setAttribute('tabindex', '0'); }catch(e){} });

    input.addEventListener('input', function(){
      const q = (this.value || '').trim().toLowerCase();
      if(!q){
        box.classList.add('hidden');
        hidden.value = '';
        return;
      }
      let shown = 0;
      items.forEach(it => {
        const text = it.textContent.trim().toLowerCase();
        if(text.indexOf(q) !== -1 && shown < 8){
          it.style.display = '';
          shown += 1;
        } else {
          it.style.display = 'none';
        }
      });
      if(shown) box.classList.remove('hidden'); else box.classList.add('hidden');
      hidden.value = '';
    });

    // Keyboard navigation: ArrowDown focuses first visible suggestion, Enter selects
    input.addEventListener('keydown', function(e){
      if(e.key === 'ArrowDown'){
        e.preventDefault();
        const first = items.find(it => it.style.display !== 'none');
        if(first){ first.focus(); }
      } else if(e.key === 'Enter'){
        // If suggestions visible, pick the first visible one
        const first = items.find(it => it.style.display !== 'none');
        if(first){ e.preventDefault(); first.click(); }
      }
    });

    items.forEach(it => {
      it.addEventListener('click', function(){
      const txt = this.textContent.replace(/\s*\(\d+\)$/, '').trim();
      input.value = txt;
      hidden.value = this.dataset.id || '';
      box.classList.add('hidden');
      });
      // support keyboard navigation on suggestions
      it.addEventListener('keydown', function(ev){
        if(ev.key === 'Enter'){
          ev.preventDefault(); this.click();
          return;
        }
        if(ev.key === 'ArrowDown'){
          ev.preventDefault();
          // focus next visible
          const idx = items.indexOf(this);
          for(let i = idx+1; i < items.length; i++){
            if(items[i].style.display !== 'none'){ items[i].focus(); break; }
          }
        }
        if(ev.key === 'ArrowUp'){
          ev.preventDefault();
          const idx = items.indexOf(this);
          for(let i = idx-1; i >= 0; i--){
            if(items[i].style.display !== 'none'){ items[i].focus(); break; }
          }
        }
      });
    });

    document.addEventListener('click', function(e){
      if(!box.contains(e.target) && e.target !== input){
        box.classList.add('hidden');
      }
    });

    input.addEventListener('keydown', function(e){ if(e.key === 'Escape') box.classList.add('hidden'); });
  }

  function initPlaylistConfirmation(){
    try{
      const page = document.getElementById('page-data');
      const raw = page && page.dataset && page.dataset.playlists;
      const PLAYLISTS = raw ? JSON.parse(raw) : [];
      const lookup = Object.create(null);
      for(const p of PLAYLISTS){
        if(!p || !p.name) continue;
        lookup[p.name.trim().toLowerCase()] = p.tracks || p.track_count || 0;
      }
      function existsCount(name){ if(!name) return 0; return lookup[name.trim().toLowerCase()] || 0; }

      // Use a modal for confirmations when cleaning; otherwise fall back to
      // a simple confirm prompt for other forms.
      const modal = document.getElementById('confirm-modal');
      const modalMsg = modal && modal.querySelector('#confirm-modal-message');
      const modalOk = modal && document.getElementById('confirm-modal-ok');
      const modalCancel = modal && document.getElementById('confirm-modal-cancel');

      document.querySelectorAll('form.ajax').forEach(form => {
        form.addEventListener('submit', function(e){
          const candidates = ['name','queue_name','clean_playlist_name','liked_name'];
          let val = '';
          for(const n of candidates){
            const el = form.querySelector('[name="' + n + '"]');
            if(el && el.value && el.value.trim()){ val = el.value.trim(); break; }
          }
          if(!val) return;

          // For the clean form we will check existence of the target cleaned
          // playlist name ("Cleaned: {original}") rather than the original
          // playlist name. If the cleaned name exists, show an in-page modal
          // asking whether to overwrite. If confirmed, set the hidden
          // overwrite input and submit.
          if(form.classList && form.classList.contains('clean-panel')){
            // Prefer explicit selection: if a hidden playlist id is present,
            // look up the canonical name from page-data.
            const hid = form.querySelector('#clean_playlist');
            const typed = form.querySelector('#clean_playlist_name');
            let originalName = typed && typed.value && typed.value.trim();
            const page = document.getElementById('page-data');
            const raw = page && page.dataset && page.dataset.playlists;
            const PLAYLISTS = raw ? JSON.parse(raw) : [];
            if(hid && hid.value){
              const found = PLAYLISTS.find(p => p.id === hid.value);
              if(found && found.name) originalName = found.name;
            }
            if(!originalName) return;
            const checkName = `Cleaned: ${originalName}`;
            const cnt = existsCount(checkName);
            if(cnt){
              e.preventDefault();
              e.stopImmediatePropagation();
              // show modal
              if(modal && modalMsg){
                modalMsg.textContent = `A playlist named "${checkName}" already exists with ${cnt} tracks. Overwrite it?`;
                modal.classList.remove('hidden');
                modal.setAttribute('aria-hidden', 'false');
              }

              // accessibility: save previously focused element to restore later
              const previouslyFocused = document.activeElement;

              // focus-trap and keyboard handling
              const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
              const panel = modal && modal.querySelector('.modal-panel');
              const getFocusable = () => panel ? Array.from(panel.querySelectorAll(focusableSelector)).filter(el => !el.hasAttribute('disabled') && el.offsetParent !== null) : [];

              const onKeyDown = function(ev){
                if(ev.key === 'Escape'){
                  ev.preventDefault();
                  onCancel();
                  return;
                }
                if(ev.key === 'Enter'){
                  // Enter confirms
                  ev.preventDefault();
                  onOk();
                  return;
                }
                if(ev.key === 'Tab'){
                  const focusables = getFocusable();
                  if(focusables.length === 0) return;
                  const idx = focusables.indexOf(document.activeElement);
                  if(ev.shiftKey){
                    if(idx === 0 || document.activeElement === modal){
                      ev.preventDefault();
                      focusables[focusables.length - 1].focus();
                    }
                  } else {
                    if(idx === focusables.length - 1){
                      ev.preventDefault();
                      focusables[0].focus();
                    }
                  }
                }
              };

              // wire up ok/cancel with cleanup
              const onOk = async function(){
                // set hidden overwrite field
                const ow = form.querySelector('#clean_overwrite');
                if(ow) ow.value = '1';
                // hide modal and remove listeners
                if(modal){ modal.classList.add('hidden'); modal.setAttribute('aria-hidden','true'); }
                modalOk && modalOk.removeEventListener('click', onOk);
                modalCancel && modalCancel.removeEventListener('click', onCancel);
                document.removeEventListener('keydown', onKeyDown);

                // Perform AJAX submit directly so we don't depend on other
                // scripts having attached submit handlers yet. This mirrors
                // the behavior in common.js:initForms for AJAX forms.
                try{
                    // create a small percentage indicator next to the form button
                    let percEl = null; let percTimer = null; let percBtn = null;
                    try{
                      percBtn = form.querySelector('button[type=submit], button:not([type])');
                      if(percBtn){
                        percEl = document.createElement('span');
                        percEl.className = 'ajax-perc';
                        percEl.textContent = '0%';
                        percBtn.insertAdjacentElement('afterend', percEl);
                        // determine total from page-data
                        let total = 100;
                        const page = document.getElementById('page-data');
                        const raw = page && page.dataset && page.dataset.playlists;
                        const PLAYLISTS = raw ? JSON.parse(raw) : [];
                        const hid = form.querySelector('#clean_playlist');
                        const pid = hid && hid.value ? hid.value : null;
                        if(pid){
                          const found = PLAYLISTS.find(p => p.id === pid);
                          if(found && found.tracks) total = Number(found.tracks) || total;
                        }
                        const targetCap = 95;
                        const duration = Math.min(30000, Math.max(1500, total * 60));
                        const stepMs = 200; const steps = Math.max(3, Math.floor(duration / stepMs));
                        let current = 0; const delta = targetCap / steps;
                        percTimer = setInterval(()=>{ current = Math.min(targetCap, current + delta); percEl.textContent = Math.floor(current) + '%'; }, stepMs);
                        percBtn.__percTimer = percTimer; percBtn.__percEl = percEl;
                      }
                    }catch(err){/* ignore */}
                    // show working state
                    try{ window.UI && window.UI.setFormWorking && window.UI.setFormWorking(form); }catch(e){}
                  const formData = new FormData(form);
                  const resp = await fetch(form.action, {
                    method: form.method || 'POST',
                    body: formData,
                    credentials: 'same-origin',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                  });
                  const text = await resp.text();
                  let handled = false;
                  try{
                    const j = JSON.parse(text);
                    if(j){
                      if(j.task_id){
                        handled = true;
                        const taskId = j.task_id;
                        // stop the simulated percentage timer if present
                        try{ if(percBtn && percBtn.__percTimer){ clearInterval(percBtn.__percTimer); delete percBtn.__percTimer; } }catch(e){}
                        const poll = async ()=>{
                          try{
                            const r = await fetch(`/clean_progress/${taskId}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' }});
                            if(!r.ok){ window.UI && window.UI.makeToast && window.UI.makeToast('Progress check failed', 'error', 3000); return; }
                            const p = await r.json();
                            if(!p || !p.ok){ window.UI && window.UI.makeToast && window.UI.makeToast(p && p.error ? p.error : 'Progress error', 'error', 3000); return; }
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
                              if(percBtn && percBtn.__percEl){ const el = percBtn.__percEl; el.textContent = '100%'; setTimeout(()=>{ el.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }, 700); }
                              window.UI && window.UI.makeToast && window.UI.makeToast(p.message || 'Clean finished', 'success', 4000);
                              return;
                            }
                            if(p.status === 'error'){
                              window.UI && window.UI.makeToast && window.UI.makeToast(p.message || 'Clean failed', 'error', 5000);
                              if(percBtn && percBtn.__percEl){ try{ percBtn.__percEl.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }catch(e){} }
                              return;
                            }
                            setTimeout(poll, 900);
                          }catch(err){ console && console.error && console.error('poll progress', err); setTimeout(poll, 1500); }
                        };
                        setTimeout(poll, 500);
                      } else if(j.message || j.msg){
                        const m = j.message || j.msg;
                        const t = (j.ok === false) ? 'error' : 'success';
                        window.UI && window.UI.makeToast && window.UI.makeToast(m, t, 4000);
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
                      window.UI && window.UI.makeToast && window.UI.makeToast(flashEl.textContent.trim(), type, 4000);
                    } else if(resp.ok){
                      window.UI && window.UI.makeToast && window.UI.makeToast('Done', 'success', 3000);
                    } else {
                      window.UI && window.UI.makeToast && window.UI.makeToast('Request failed', 'error', 4000);
                    }
                  }
                }catch(err){
                  console && console.error && console.error(err);
                  window.UI && window.UI.makeToast && window.UI.makeToast('Request failed', 'error', 4000);
                }finally{
                  // clear percentage indicator
                  try{ if(percTimer) clearInterval(percTimer); if(percBtn && percBtn.__percEl){ const el = percBtn.__percEl; el.textContent = '100%'; setTimeout(()=>{ el.remove(); delete percBtn.__percEl; delete percBtn.__percTimer; }, 700); } }catch(e){}
                  try{ window.UI && window.UI.clearFormWorking && window.UI.clearFormWorking(form); }catch(e){}
                }
              };
              const onCancel = function(){
                if(modal){ modal.classList.add('hidden'); modal.setAttribute('aria-hidden','true'); }
                modalOk && modalOk.removeEventListener('click', onOk);
                modalCancel && modalCancel.removeEventListener('click', onCancel);
                document.removeEventListener('keydown', onKeyDown);
                try{ if(previouslyFocused && previouslyFocused.focus) previouslyFocused.focus(); }catch(err){}
                window.UI && window.UI.makeToast && window.UI.makeToast('Canceled', 'info', 1500);
              };

              modalOk && modalOk.addEventListener('click', onOk);
              modalCancel && modalCancel.addEventListener('click', onCancel);

              // set initial focus to the OK button and attach keydown handler
              try{
                modalOk && modalOk.focus();
                document.addEventListener('keydown', onKeyDown);
              }catch(err){}

              return false;
            }
            // otherwise allow submit to proceed
            return;
          }

          // non-clean panels: simple confirm
          let checkName = val;
          const cnt = existsCount(checkName);
          if(cnt){
            const msg = `Playlist "${checkName}" already exists with ${cnt} songs. Do you wish to override it?`;
            if(!window.confirm(msg)){
              e.preventDefault();
              e.stopImmediatePropagation();
              window.UI && window.UI.makeToast && window.UI.makeToast('Canceled', 'info', 1500);
              return false;
            }
          }
        }, true);
      });
    }catch(err){ console && console.error && console.error('playlist confirmation setup failed', err); }
  }

  function initCompareButtons(){
    const input = document.getElementById('compare_user_input');
    const btn = document.getElementById('compare_btn');
    if(!input || !btn) return;
    btn.addEventListener('click', async function(){
      // If this button already has a result URL, open it instead of re-running the fetch
      if(btn.dataset && btn.dataset.resultUrl){
        try{ window.open(btn.dataset.resultUrl, '_blank'); }catch(e){ window.location.href = btn.dataset.resultUrl; }
        return;
      }
      const user = input.value && input.value.trim();
      if(!user){ window.UI && window.UI.makeToast && window.UI.makeToast('Enter a user id or URL', 'info', 1800); return; }
      try{ window.UI && window.UI.setButtonWorking && window.UI.setButtonWorking(btn); }catch(e){}
      try{
        const res = await fetch('/compare_fetch', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({compare_user: user}) });
        const data = await res.json();
        if(!res.ok || !data || !data.ok){
          const msg = (data && data.error) ? data.error : 'Failed to fetch';
          window.UI && window.UI.makeToast && window.UI.makeToast(msg, 'error', 2500);
          return;
        }
        // Keep the same button element and label. Set it to a ready state.
        btn.textContent = 'View result';
        btn.dataset.resultUrl = data.url;
        btn.classList.add('ready');
        // add a hint toast
        window.UI && window.UI.makeToast && window.UI.makeToast('Comparison ready — click to view', 'success', 2200);
      }catch(err){
        console && console.error && console.error('compare fetch error', err);
        window.UI && window.UI.makeToast && window.UI.makeToast('Network error', 'error', 1800);
      }finally{
        try{ window.UI && window.UI.clearButtonWorking && window.UI.clearButtonWorking(btn); }catch(e){}
      }
    });
  }

  // expose toggle functions for inline attributes to keep migration minimal
  window.togglePanel = togglePanel;
  window.toggleDetails = toggleDetails;

  document.addEventListener('DOMContentLoaded', function(){
    initTypeahead();
    initPlaylistConfirmation();
    initCompareButtons();
  });

})();
