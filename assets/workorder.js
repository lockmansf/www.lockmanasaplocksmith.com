/* LOCKMAN work orders: owner dashboard (PIN) + customer signing page. Talks to the Google Apps Script web app. */
(function () {
  var root = document.getElementById('wo-app');
  if (!root) return;
  var API = root.dataset.api;
  var PAY = { zelle: root.dataset.zelle || '', venmo: root.dataset.venmo || '', cashapp: root.dataset.cashapp || '', review: root.dataset.review || '' };
  var TERMS = document.getElementById('wo-terms-text').textContent.trim();
  var qs = new URLSearchParams(location.search);
  var MOBILE = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  var $ = function (s, el) { return (el || document).querySelector(s); };

  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function money(v) { var n = Number(v); return v === '' || v == null || isNaN(n) ? '' : '$' + n.toFixed(2); }
  function show(id) { root.querySelectorAll('[data-view]').forEach(function (v) { v.hidden = v.dataset.view !== id; }); window.scrollTo(0, 0); }
  function msg(el, text, bad) { el.textContent = text; el.className = 'wo-msg' + (bad ? ' bad' : ''); }

  function call(body) {
    if (!API) return Promise.reject(new Error('The work order system is not connected yet.'));
    return fetch(API, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (!d.ok) throw new Error(d.error || 'Something went wrong'); return d; });
  }

  function customerLink(id, token) { return location.origin + location.pathname + '?j=' + encodeURIComponent(id) + '&t=' + encodeURIComponent(token); }

  // ---------------------------------------------------------------- image + signature helpers
  function shrink(file, max) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var k = Math.min(1, max / Math.max(img.width, img.height));
        var c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(img.src);
        resolve(c.toDataURL('image/jpeg', 0.82));
      };
      img.onerror = function () { reject(new Error('Could not read that photo. Try again.')); };
      img.src = URL.createObjectURL(file);
    });
  }

  function signaturePad(canvas) {
    var ctx = canvas.getContext('2d'), drawing = false, dirty = false, last = null;
    function size() {
      var r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      canvas.width = r.width * dpr; canvas.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineWidth = 2.6; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#111';
      dirty = false;
    }
    function pos(e) { var r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    canvas.addEventListener('pointerdown', function (e) { drawing = true; last = pos(e); canvas.setPointerCapture(e.pointerId); e.preventDefault(); });
    canvas.addEventListener('pointermove', function (e) {
      if (!drawing) return;
      var p = pos(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; dirty = true; e.preventDefault();
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (t) { canvas.addEventListener(t, function () { drawing = false; }); });
    size();
    return {
      clear: size,
      empty: function () { return !dirty; },
      data: function () {
        var out = document.createElement('canvas'); out.width = canvas.width; out.height = canvas.height;
        var o = out.getContext('2d'); o.fillStyle = '#fff'; o.fillRect(0, 0, out.width, out.height); o.drawImage(canvas, 0, 0);
        return out.toDataURL('image/png');
      }
    };
  }

  // ---------------------------------------------------------------- customer page
  function vehicleJob(t) { return /car/i.test(t || ''); }
  function safeJob(t) { return /safe/i.test(t || ''); }

  function payBlock(id, amount) {
    var a = Number(amount) || 0, rows = [];
    if (PAY.venmo) rows.push('<a class="btn btn-ghost" href="https://venmo.com/u/' + encodeURIComponent(PAY.venmo) + '?txn=pay&amount=' + a.toFixed(2) + '&note=' + encodeURIComponent(id) + '" rel="noopener">Pay with Venmo</a>');
    if (PAY.cashapp) rows.push('<a class="btn btn-ghost" href="https://cash.app/$' + encodeURIComponent(PAY.cashapp) + '/' + a.toFixed(2) + '" rel="noopener">Pay with Cash App</a>');
    if (PAY.zelle) rows.push('<p><strong>Zelle:</strong> ' + esc(PAY.zelle) + ' (note: ' + esc(id) + ')</p><p><img src="/assets/img/zelle-qr.png" alt="Zelle QR code for Lockman ASAP Locksmith Inc" width="200" height="200"><br><small>Scan in your bank app to pay with Zelle</small></p>');
    rows.push('<p>Cash or card in person is also fine.</p>');
    return '<div class="wo-pay">' + rows.join('') + '</div>';
  }

  function customer(id, token) {
    show('loading');
    call({ action: 'get', id: id, token: token }).then(function (j) {
      if (j.invoice) {
        var inv = j.invoice;
        $('#wo-invoice').innerHTML = '<h2 class="comic">' + (inv.paid ? 'Receipt' : 'Invoice') + ' ' + esc(j.id) + '</h2>' +
          '<p>' + esc(j.job_type) + (inv.address ? ' at ' + esc(inv.address) : '') + (inv.vehicle ? ' (' + esc(inv.vehicle) + ')' : '') + '</p>' +
          '<p class="wo-total">Total: ' + money(inv.final_price) + '</p>' +
          (inv.paid ? '<p class="wo-paid">PAID' + (inv.payment_method ? ' by ' + esc(inv.payment_method) : '') + '. Thank you!</p>' : payBlock(j.id, inv.final_price)) +
          (PAY.review ? '<div class="wo-review"><p><strong>Happy with the service?</strong> A quick Google review helps a small local business a lot.</p><a class="btn btn-call btn-lg" href="' + esc(PAY.review) + '" target="_blank" rel="noopener">&#11088; Leave a Google review</a></div>' : '');
        return show('invoice');
      }
      if (j.status !== 'Sent') { $('#wo-done-text').textContent = 'This work order (' + j.id + ') is already signed. Thank you!'; return show('done'); }
      $('#wo-job-type').textContent = j.job_type;
      $('#wo-job-id').textContent = j.id;
      $('#wo-job-notes').textContent = j.notes || '';
      var hasPrice = j.price !== '' && j.price != null;
      $('#wo-job-price').textContent = hasPrice ? money(j.price) : 'Confirmed with you before work starts';
      $('#wo-price-ok-row').hidden = !hasPrice;
      $('#wo-price-ok').required = hasPrice;
      root.querySelectorAll('[data-for="car"]').forEach(function (el) { el.hidden = !vehicleJob(j.job_type); el.querySelectorAll('input').forEach(function (i) { i.required = vehicleJob(j.job_type) && i.dataset.req === '1'; }); });
      root.querySelectorAll('[data-for="safe"]').forEach(function (el) { el.hidden = !safeJob(j.job_type); });
      root.querySelectorAll('[data-for="property"]').forEach(function (el) { el.hidden = vehicleJob(j.job_type); });
      show('sign');
      var pad = signaturePad($('#wo-sig'));
      $('#wo-sig-clear').onclick = function () { pad.clear(); };
      $('#wo-sign-form').onsubmit = function (ev) {
        ev.preventDefault();
        var f = ev.target, out = $('#wo-sign-msg');
        if (pad.empty()) return msg(out, 'Please sign in the box.', true);
        var idFile = f.id_photo.files[0];
        if (!idFile && !f.id_in_person.checked) return msg(out, 'Add a photo of your ID, or tick the box that you will show your ID to the technician.', true);
        var btn = f.querySelector('button[type=submit]'); btn.disabled = true;
        msg(out, 'Sending... please wait.');
        var docFiles = [].slice.call(f.docs.files || []).slice(0, 4);
        Promise.all([idFile ? shrink(idFile, 1600) : Promise.resolve('')].concat(docFiles.map(function (d) { return shrink(d, 1600); }))).then(function (imgs) {
          var veh = [f.v_year.value, f.v_make.value, f.v_model.value, f.v_color.value].filter(Boolean).join(' ');
          return call({
            action: 'sign', id: id, token: token, id_photo: imgs[0], id_in_person: !idFile && f.id_in_person.checked, docs: imgs.slice(1), signature: pad.data(), terms_text: TERMS,
            customer: {
              customer_name: f.name.value.trim(), phone: f.phone.value.trim(), email: f.email.value.trim(), dob: f.dob.value,
              address: f.address.value.trim(), id_type: f.id_type.value, id_number: f.id_number.value.trim(),
              relation: vehicleJob(j.job_type) ? 'Vehicle owner / authorized driver' : f.relation.value,
              vehicle: veh, plate: f.plate.value.trim(), vin: f.vin.value.trim(), safe_info: f.safe_info.value.trim()
            }
          });
        }).then(function (r) {
          $('#wo-done-text').textContent = 'Thank you! Work order ' + r.id + ' is signed. ' + (f.email.value ? 'A copy was emailed to you.' : '');
          show('done');
        }).catch(function (err) { btn.disabled = false; msg(out, err.message, true); });
      };
    }).catch(function (err) { $('#wo-done-text').textContent = err.message; show('done'); });
  }

  // ---------------------------------------------------------------- owner dashboard
  function owner() {
    var pin = store('wo-pin');
    if (!pin) return show('login');
    show('loading');
    call({ action: 'login', pin: pin }).then(function (d) {
      var sel = $('#wo-new-type');
      sel.innerHTML = d.job_types.map(function (t) { return '<option>' + esc(t) + '</option>'; }).join('');
      show('owner');
      refresh();
    }).catch(function (err) { store('wo-pin', null); show('login'); msg($('#wo-login-msg'), err.message, true); });
  }

  function refresh() {
    var box = $('#wo-jobs');
    box.innerHTML = '<p>Loading jobs...</p>';
    call({ action: 'list', pin: store('wo-pin') }).then(function (d) {
      if (!d.jobs.length) { box.innerHTML = '<p>No jobs yet.</p>'; return; }
      box.innerHTML = d.jobs.map(function (j) {
        var link = customerLink(j.id, j.token);
        return '<div class="card wo-job"><p class="wo-job-head"><strong>' + esc(j.id) + '</strong> &middot; ' + esc(j.job_type) +
          ' <span class="wo-status s-' + esc(String(j.status).toLowerCase()) + '">' + esc(j.status) + '</span></p>' +
          (j.status === 'Signed' && j.id_check && j.id_check !== 'Photo uploaded' ? '<p class="wo-msg bad">Check ID in person before starting</p>' : '') +
          '<p>' + esc(j.customer_name || 'Waiting for customer') + (j.address ? ' &middot; ' + esc(j.address) : '') + '<br>' + esc(j.created) +
          (j.final_price !== '' ? ' &middot; ' + money(j.final_price) : (j.price !== '' ? ' &middot; est. ' + money(j.price) : '')) + '</p>' +
          '<div class="btn-row">' +
          (j.status === 'Sent' ? '<a class="btn btn-call" href="' + esc(link) + '">Customer signs here</a><button class="btn btn-ghost" data-copy="' + esc(link) + '">Copy link</button>' : '') +
          (j.status === 'Signed' ? '<button class="btn btn-call" data-finish="' + esc(j.id) + '" data-token="' + esc(j.token) + '" data-phone="' + esc(j.phone || '') + '" data-email="' + esc(j.email || '') + '" data-price="' + esc(j.price) + '" data-idcheck="' + esc(j.id_check) + '">&#9989; Job done &rarr; invoice</button>' : '') +
          (j.status === 'Invoiced' || j.status === 'Paid' ? '<a class="btn btn-ghost" href="' + esc(link) + '">View invoice</a><button class="btn btn-ghost" type="button" data-sendinv="' + esc(j.id) + '" data-token="' + esc(j.token) + '" data-phone="' + esc(j.phone || '') + '">Send invoice</button>' : '') +
          (j.folder_url ? '<a class="btn btn-ghost" href="' + esc(j.folder_url) + '" target="_blank" rel="noopener">Files</a>' : '') +
          '</div></div>';
      }).join('');
    }).catch(function (err) { box.innerHTML = '<p class="wo-msg bad">' + esc(err.message) + '</p>'; });
  }

  function shareRow(text, phone) {
    var digits = (phone || '').replace(/\D/g, '');
    if (digits.length === 10) digits = '1' + digits;
    return (MOBILE ? '<a class="btn btn-ghost" href="sms:' + (digits ? '+' + digits : '') + (/iPhone|iPad/.test(navigator.userAgent) ? '&' : '?') + 'body=' + encodeURIComponent(text) + '">Send by text</a>'
        : '<button class="btn btn-ghost" type="button" data-copy="' + esc(text) + '" data-note="Copied! Text messages open only on a phone. Paste this into a text or email.">Copy text message</button>') +
      '<a class="btn btn-wa" href="https://wa.me/' + digits + '?text=' + encodeURIComponent(text) + '" rel="noopener">WhatsApp</a>';
  }

  function invoiceCard(id, token, phone, status, emailedTo) {
    var link = customerLink(id, token);
    var text = 'Lockman ASAP Locksmith: thank you! Your ' + (status === 'Paid' ? 'receipt' : 'invoice') + ' ' + id + ' is here: ' + link;
    $('#wo-created').innerHTML = '<div class="card"><h3>' + (status === 'Paid' ? 'Receipt' : 'Invoice') + ' ' + esc(id) + ' is ready.</h3>' + (emailedTo ? '<p>&#9993; Emailed to ' + esc(emailedTo) + '</p>' : '') + '<p>Send it to the customer by text:</p><div class="btn-row">' +
      '<a class="btn btn-call" href="' + esc(link) + '">Show customer on my phone</a>' + shareRow(text, phone) +
      '<button class="btn btn-ghost" data-copy="' + esc(link) + '">Copy link</button></div></div>';
    $('#wo-created').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function sendButtons(id, token, phone) {
    var link = customerLink(id, token);
    var text = 'Lockman ASAP Locksmith: please fill in and sign your work order ' + id + ' here: ' + link;
    var digits = (phone || '').replace(/\D/g, '');
    if (digits.length === 10) digits = '1' + digits;
    $('#wo-created').innerHTML = '<div class="card"><h3>Work order ' + esc(id) + ' is ready</h3><div class="btn-row">' +
      '<a class="btn btn-call" href="' + esc(link) + '">Customer signs on my phone</a>' +
      (MOBILE ? '<a class="btn btn-ghost" href="sms:' + (digits ? '+' + digits : '') + (/iPhone|iPad/.test(navigator.userAgent) ? '&' : '?') + 'body=' + encodeURIComponent(text) + '">Send by text</a>'
        : '<button class="btn btn-ghost" type="button" data-copy="' + esc(text) + '" data-note="Copied! Text messages open only on a phone. Paste this into a text or email.">Copy text message</button>') +
      '<a class="btn btn-wa" href="https://wa.me/' + digits + '?text=' + encodeURIComponent(text) + '" rel="noopener">WhatsApp</a>' +
      '<button class="btn btn-ghost" data-copy="' + esc(link) + '">Copy link</button></div></div>';
  }

  root.addEventListener('click', function (ev) {
    var c = ev.target.closest('[data-copy]');
    if (c) {
      navigator.clipboard.writeText(c.dataset.copy).then(function () {
        c.textContent = 'Copied!';
        if (c.dataset.note) { var n = document.createElement('p'); n.className = 'wo-msg'; n.textContent = c.dataset.note; c.parentNode.after(n); c.removeAttribute('data-note'); }
      });
      return;
    }
    var si = ev.target.closest('[data-sendinv]');
    if (si) { invoiceCard(si.dataset.sendinv, si.dataset.token, si.dataset.phone, 'Invoiced'); return; }
    var fin = ev.target.closest('[data-finish]');
    if (fin) {
      var f = $('#wo-finish-form');
      f.job.value = fin.dataset.finish; f.final_price.value = fin.dataset.price || '';
      f.dataset.token = fin.dataset.token; f.dataset.phone = fin.dataset.phone;
      f.email.value = fin.dataset.email || ''; f.send_email.checked = !!fin.dataset.email;
      $('#wo-finish-id').textContent = fin.dataset.finish;
      var inPerson = fin.dataset.idcheck && fin.dataset.idcheck !== 'Photo uploaded';
      $('#wo-idv-row').hidden = !inPerson; f.id_verified.checked = false; f.id_verified.required = inPerson;
      msg($('#wo-finish-msg'), '');
      show('finish');
    }
  });

  $('#wo-login-form').onsubmit = function (ev) { ev.preventDefault(); store('wo-pin', ev.target.pin.value.trim()); owner(); };
  $('#wo-logout').onclick = function () { store('wo-pin', null); show('login'); };
  $('#wo-refresh').onclick = refresh;
  $('#wo-new-form').onsubmit = function (ev) {
    ev.preventDefault();
    var f = ev.target, b = f.querySelector('button[type=submit]'); b.disabled = true;
    call({ action: 'create', pin: store('wo-pin'), job_type: f.job_type.value, price: f.price.value, notes: f.notes.value, phone: f.phone.value })
      .then(function (d) { sendButtons(d.id, d.token, f.phone.value); f.reset(); refresh(); })
      .catch(function (err) { $('#wo-created').innerHTML = '<p class="wo-msg bad">' + esc(err.message) + '</p>'; })
      .then(function () { b.disabled = false; });
  };
  $('#wo-finish-form').onsubmit = function (ev) {
    ev.preventDefault();
    var f = ev.target, b = f.querySelector('button[type=submit]'); b.disabled = true;
    msg($('#wo-finish-msg'), 'Creating invoice...');
    call({ action: 'finish', pin: store('wo-pin'), id: f.job.value, final_price: f.final_price.value, payment_method: f.method.value,
      paid: f.paid.checked, id_verified: f.id_verified.checked, email: f.email.value, send_email: f.send_email.checked, payments: PAY })
      .then(function (r) { show('owner'); refresh(); invoiceCard(f.job.value, f.dataset.token, f.dataset.phone, r.status, r.emailed ? f.email.value : ''); })
      .catch(function (err) { msg($('#wo-finish-msg'), err.message, true); })
      .then(function () { b.disabled = false; });
  };
  $('#wo-finish-cancel').onclick = function () { show('owner'); };

  if (qs.get('j') && qs.get('t')) customer(qs.get('j'), qs.get('t'));
  else owner();
})();
