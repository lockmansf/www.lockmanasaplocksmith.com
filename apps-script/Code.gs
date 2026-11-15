/**
 * LOCKMAN work orders: free backend on the owner's own Google account.
 *
 * Saves each job in Google Drive (folder "LOCKMAN Work Orders", one subfolder per job: ID photo,
 * documents, signature, signed work order PDF, invoice PDF) and logs it in the Google Sheet
 * "LOCKMAN Work Orders". The website page /work-order/ talks to this script.
 *
 * One-time setup (in script.google.com):
 *   1. Run setup() once and allow access.
 *   2. Project Settings > Script properties: set ADMIN_PIN (owner's PIN, 4+ digits).
 *   3. Deploy > New deployment > Web app: Execute as "Me", Who has access "Anyone". Copy the /exec URL
 *      into config.json "work_order_api".
 */

var BUSINESS = {
  name: 'Lockman ASAP Locksmith Inc',
  license: 'LCO 8611',
  phone: '(415) 806-7343',
  email: 'billinglockman@gmail.com',
  site: 'https://lockmanasaplocksmith.com',
  review: 'https://g.page/r/CQihC5bClvdNEBM/review',
  city: 'San Francisco, CA'
};

var COLUMNS = ['id', 'token', 'status', 'created', 'job_type', 'price', 'job_notes', 'customer_name', 'phone', 'email',
  'dob', 'address', 'id_type', 'id_number', 'relation', 'vehicle', 'plate', 'vin', 'safe_info', 'signed_at',
  'final_price', 'payment_method', 'paid', 'invoiced_at', 'folder_url', 'work_order_pdf', 'invoice_pdf',
  'id_check', 'id_verified_onsite'];

var JOB_TYPES = ['Car lockout', 'House lockout', 'Business lockout', 'Safe lockout', 'Rekey house', 'Rekey business',
  'Car key made', 'Lock change / repair', 'Other'];

function props() { return PropertiesService.getScriptProperties(); }

function setup() {
  var p = props();
  if (!p.getProperty('ROOT_FOLDER_ID')) {
    var folder = DriveApp.createFolder('LOCKMAN Work Orders');
    p.setProperty('ROOT_FOLDER_ID', folder.getId());
  }
  if (!p.getProperty('SHEET_ID')) {
    var ss = SpreadsheetApp.create('LOCKMAN Work Orders');
    var sh = ss.getSheets()[0];
    sh.setName('Jobs');
    sh.appendRow(COLUMNS);
    sh.setFrozenRows(1);
    DriveApp.getFileById(ss.getId()).moveTo(DriveApp.getFolderById(p.getProperty('ROOT_FOLDER_ID')));
    p.setProperty('SHEET_ID', ss.getId());
  }
  if (!p.getProperty('ADMIN_PIN')) p.setProperty('ADMIN_PIN', 'CHANGE-ME');
  Logger.log('Folder: ' + DriveApp.getFolderById(p.getProperty('ROOT_FOLDER_ID')).getUrl());
}

// ------------------------------------------------------------------ web entry points

function doGet() {
  return json({ ok: true, service: 'LOCKMAN work orders' });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var req = JSON.parse(e.postData.contents);
    var a = req.action;
    if (a === 'get') return json(getJob(req));
    if (a === 'sign') return json(sign(req));
    // owner-only actions
    if (!checkPin(req.pin)) return json({ ok: false, error: 'Wrong PIN' });
    if (a === 'login') return json({ ok: true, job_types: JOB_TYPES });
    if (a === 'create') return json(createJob(req));
    if (a === 'list') return json(listJobs());
    if (a === 'finish') return json(finish(req));
    return json({ ok: false, error: 'Unknown action' });
  } catch (err) {
    return json({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function json(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function checkPin(pin) {
  var real = props().getProperty('ADMIN_PIN');
  return real && real !== 'CHANGE-ME' && String(pin || '') === real;
}

// ------------------------------------------------------------------ sheet helpers

function sheet() {
  var sh = SpreadsheetApp.openById(props().getProperty('SHEET_ID')).getSheetByName('Jobs');
  if (sh.getLastColumn() < COLUMNS.length) sh.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS]);  // add new columns
  return sh;
}

function findRow(id) {
  var sh = sheet();
  var ids = sh.getRange(2, 1, Math.max(1, sh.getLastRow() - 1), 1).getValues();
  for (var i = 0; i < ids.length; i++) if (ids[i][0] === id) return i + 2;
  return -1;
}

function readRow(r) {
  var vals = sheet().getRange(r, 1, 1, COLUMNS.length).getValues()[0];
  var o = {};
  COLUMNS.forEach(function (c, i) { o[c] = vals[i]; });
  return o;
}

function writeRow(r, o) {
  sheet().getRange(r, 1, 1, COLUMNS.length).setValues([COLUMNS.map(function (c) { return o[c] === undefined ? '' : o[c]; })]);
}

function jobByToken(req) {
  var r = findRow(String(req.id || ''));
  if (r < 0) throw new Error('Job not found');
  var o = readRow(r);
  if (String(o.token) !== String(req.token || '')) throw new Error('Job not found');
  return { r: r, o: o };
}

function money(v) {
  var n = Number(v);
  return isNaN(n) || v === '' ? '' : '$' + n.toFixed(2);
}

// ------------------------------------------------------------------ actions

function createJob(req) {
  var tz = Session.getScriptTimeZone();
  var now = new Date();
  var id = 'WO-' + Utilities.formatDate(now, tz, 'yyMMdd') + '-' + Math.floor(1000 + Math.random() * 9000);
  var token = Utilities.getUuid().replace(/-/g, '').slice(0, 20);
  var job = {
    id: id, token: token, status: 'Sent', created: Utilities.formatDate(now, tz, 'yyyy-MM-dd HH:mm'),
    job_type: req.job_type || 'Other', price: req.price === '' || req.price == null ? '' : Number(req.price),
    job_notes: req.notes || '', phone: req.phone || '', email: req.email || ''
  };
  sheet().appendRow(COLUMNS.map(function (c) { return job[c] === undefined ? '' : job[c]; }));
  return { ok: true, id: id, token: token };
}

function getJob(req) {
  var j = jobByToken(req).o;
  var out = {
    ok: true, id: j.id, status: j.status, job_type: j.job_type, price: j.price, notes: j.job_notes,
    customer_name: j.customer_name, created: j.created
  };
  if (j.status === 'Invoiced' || j.status === 'Paid') {
    out.invoice = { final_price: j.final_price, payment_method: j.payment_method, paid: j.paid === true || j.paid === 'TRUE',
      invoiced_at: j.invoiced_at, address: j.address, vehicle: j.vehicle };
  }
  return out;
}

function saveImage(folder, dataUrl, name) {
  if (!dataUrl) return '';
  var m = String(dataUrl).match(/^data:(image\/[a-z]+);base64,(.+)$/);
  if (!m) return '';
  var blob = Utilities.newBlob(Utilities.base64Decode(m[2]), m[1], name);
  return folder.createFile(blob).getUrl();
}

function sign(req) {
  var found = jobByToken(req);
  var j = found.o;
  if (j.status !== 'Sent') throw new Error('This work order was already signed.');
  var c = req.customer || {};
  ['customer_name', 'phone', 'dob', 'address', 'id_type', 'id_number'].forEach(function (k) {
    if (!c[k]) throw new Error('Missing ' + k);
  });
  if (!req.signature) throw new Error('Signature is required');
  if (!req.id_photo && !req.id_in_person) throw new Error('Add a photo of your ID, or confirm you will show it to the technician');
  var root = DriveApp.getFolderById(props().getProperty('ROOT_FOLDER_ID'));
  var folder = root.createFolder(j.id + ' ' + c.customer_name + ' - ' + j.job_type);
  saveImage(folder, req.id_photo, 'id-photo.jpg');
  (req.docs || []).forEach(function (d, i) { saveImage(folder, d, 'document-' + (i + 1) + '.jpg'); });
  saveImage(folder, req.signature, 'signature.png');

  var tz = Session.getScriptTimeZone();
  Object.keys(c).forEach(function (k) { if (COLUMNS.indexOf(k) >= 0 && k !== 'id' && k !== 'token') j[k] = c[k]; });
  j.id_check = req.id_photo ? 'Photo uploaded' : 'Customer will show ID to technician on site';
  j.signed_at = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm');
  j.status = 'Signed';
  j.folder_url = folder.getUrl();
  var pdf = folder.createFile(htmlPdf(workOrderHtml(j, req), j.id + ' work order.pdf'));
  j.work_order_pdf = pdf.getUrl();
  writeRow(found.r, j);

  var subject = 'Work order ' + j.id + ' signed - ' + j.job_type + ' - ' + j.customer_name;
  MailApp.sendEmail({ to: BUSINESS.email, subject: subject, body: 'Signed work order attached.\nJob folder: ' + j.folder_url,
    attachments: [pdf.getAs('application/pdf')] });
  if (j.email) {
    MailApp.sendEmail({ to: j.email, subject: 'Your work order with ' + BUSINESS.name, name: BUSINESS.name, replyTo: BUSINESS.email,
      body: 'Thank you. A copy of your signed work order is attached.\n\n' + BUSINESS.name + '\n' + BUSINESS.phone,
      attachments: [pdf.getAs('application/pdf')] });
  }
  return { ok: true, id: j.id };
}

function finish(req) {
  var r = findRow(String(req.id || ''));
  if (r < 0) throw new Error('Job not found');
  var j = readRow(r);
  if (j.status === 'Sent') throw new Error('The customer has not signed yet.');
  var tz = Session.getScriptTimeZone();
  j.final_price = Number(req.final_price);
  if (isNaN(j.final_price)) throw new Error('Enter the final price');
  if (j.id_check !== 'Photo uploaded' && !req.id_verified) throw new Error('Check the customer ID in person and tick the ID box first.');
  if (req.id_verified) j.id_verified_onsite = 'Yes, ' + Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm');
  j.payment_method = req.payment_method || '';
  j.paid = !!req.paid;
  j.invoiced_at = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm');
  j.status = j.paid ? 'Paid' : 'Invoiced';
  var folder = DriveApp.getFileById(idFromUrl(j.work_order_pdf)).getParents().next();
  var pdf = folder.createFile(htmlPdf(invoiceHtml(j, req.payments || {}), j.id + ' invoice.pdf'));
  j.invoice_pdf = pdf.getUrl();
  writeRow(r, j);
  if (j.email) {
    MailApp.sendEmail({ to: j.email, subject: (j.paid ? 'Receipt ' : 'Invoice ') + j.id + ' from ' + BUSINESS.name,
      name: BUSINESS.name, replyTo: BUSINESS.email,
      body: (j.paid ? 'Thank you for your payment. Your receipt is attached.' : 'Your invoice is attached.') +
        '\n\nView online: ' + BUSINESS.site + '/work-order/?j=' + j.id + '&t=' + j.token +
        '\n\nHappy with the service? A quick Google review helps us a lot:\n' + BUSINESS.review + '\n\nThank you!\n' + BUSINESS.name + '\n' + BUSINESS.phone,
      attachments: [pdf.getAs('application/pdf')] });
  }
  MailApp.sendEmail({ to: BUSINESS.email, subject: 'Invoice ' + j.id + ' ' + money(j.final_price) + (j.paid ? ' PAID' : ''),
    body: 'Invoice attached.', attachments: [pdf.getAs('application/pdf')] });
  return { ok: true, id: j.id, status: j.status };
}

function listJobs() {
  var sh = sheet();
  var n = sh.getLastRow() - 1;
  if (n < 1) return { ok: true, jobs: [] };
  var start = Math.max(2, sh.getLastRow() - 39);
  var vals = sh.getRange(start, 1, sh.getLastRow() - start + 1, COLUMNS.length).getValues();
  var jobs = vals.map(function (v) {
    var o = {};
    COLUMNS.forEach(function (c, i) { o[c] = v[i]; });
    return { id: o.id, token: o.token, status: o.status, created: String(o.created), job_type: o.job_type, price: o.price,
      customer_name: o.customer_name, phone: String(o.phone || ""), address: o.address, final_price: o.final_price, folder_url: o.folder_url,
      id_check: o.id_check };
  }).reverse();
  return { ok: true, jobs: jobs };
}

function idFromUrl(u) { return String(u).match(/[-\w]{25,}/)[0]; }

// ------------------------------------------------------------------ documents

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function htmlPdf(html, name) {
  return HtmlService.createHtmlOutput(html).getBlob().getAs('application/pdf').setName(name);
}

var DOC_CSS = '<style>body{font-family:Arial,sans-serif;font-size:11pt;color:#111;margin:24px}h1{font-size:18pt;margin:0}' +
  '.hd{border-bottom:4px solid #f2c200;padding-bottom:8px;margin-bottom:12px}table{border-collapse:collapse;width:100%}' +
  'td{border:1px solid #ccc;padding:5px 7px;vertical-align:top}td.k{background:#f6f6f6;width:34%;font-weight:bold}' +
  '.small{font-size:9pt;color:#444}.total{font-size:16pt;font-weight:bold}</style>';

function header(title, j) {
  return '<div class="hd"><h1>' + esc(BUSINESS.name) + '</h1><div>' + esc(BUSINESS.city) + ' &middot; ' + esc(BUSINESS.phone) +
    ' &middot; ' + esc(BUSINESS.email) + '<br>California Locksmith License ' + esc(BUSINESS.license) + '</div>' +
    '<h2>' + esc(title) + ' ' + esc(j.id) + '</h2></div>';
}

function rows(pairs) {
  return '<table>' + pairs.filter(function (p) { return p[1] !== '' && p[1] != null; })
    .map(function (p) { return '<tr><td class="k">' + esc(p[0]) + '</td><td>' + esc(p[1]) + '</td></tr>'; }).join('') + '</table>';
}

function workOrderHtml(j, req) {
  var imgs = req.id_photo
    ? '<p><b>Customer ID photo</b><br><img src="' + req.id_photo + '" style="max-width:360px;max-height:260px"></p>'
    : '<p><b>ID photo:</b> not uploaded. Customer confirmed they have a valid photo ID and will show it to the technician on site for verification.</p>';
  (req.docs || []).forEach(function (d, i) {
    imgs += '<p><b>Document ' + (i + 1) + '</b><br><img src="' + d + '" style="max-width:360px;max-height:260px"></p>';
  });
  return DOC_CSS + header('Work Order', j) + rows([
    ['Date', j.signed_at], ['Service', j.job_type], ['Approved price', money(j.price) || 'To be confirmed before work'],
    ['Job notes', j.job_notes], ['Customer name', j.customer_name], ['Phone', j.phone], ['Email', j.email],
    ['Date of birth', j.dob], ['Service address', j.address], ['ID type / number', j.id_type + ' ' + j.id_number], ['ID check', j.id_check],
    ['Relation to property', j.relation], ['Vehicle (year, make, model, color)', j.vehicle], ['License plate', j.plate],
    ['VIN', j.vin], ['Safe', j.safe_info], ['Locksmith', BUSINESS.name + ', License ' + BUSINESS.license]
  ]) + '<p class="small">' + esc(req.terms_text || '') + '</p>' +
    '<p><b>Customer signature</b> (signed ' + esc(j.signed_at) + ')<br><img src="' + req.signature + '" style="height:110px;border-bottom:1px solid #000"></p>' +
    imgs + '<p class="small">Kept for two years as required by California Business and Professions Code 6980.55.</p>';
}

function invoiceHtml(j, pay) {
  var payLines = [];
  if (pay.zelle) payLines.push('Zelle: ' + pay.zelle);
  if (pay.venmo) payLines.push('Venmo: @' + pay.venmo);
  if (pay.cashapp) payLines.push('Cash App: $' + pay.cashapp);
  payLines.push('Cash or card in person');
  return DOC_CSS + header(j.paid ? 'Receipt' : 'Invoice', j) + rows([
    ['Invoice date', j.invoiced_at], ['Customer', j.customer_name], ['Phone', j.phone], ['Service address', j.address],
    ['Vehicle', j.vehicle], ['Service', j.job_type], ['Notes', j.job_notes], ['Work order signed', j.signed_at],
    ['ID verified on site', j.id_verified_onsite]
  ]) + '<p class="total">Total: ' + money(j.final_price) + '</p>' +
    (j.paid ? '<p class="total" style="color:#128c4a">PAID' + (j.payment_method ? ' by ' + esc(j.payment_method) : '') + '</p>'
      : '<p><b>How to pay</b><br>' + payLines.map(esc).join('<br>') + '</p><p>Please include ' + esc(j.id) + ' in the payment note.</p>') +
    '<p>Thank you for choosing ' + esc(BUSINESS.name) + '!</p>' +
    '<p><b>Happy with the service?</b> Please leave us a Google review: ' + esc(BUSINESS.review) + '</p>';
}
