/* MAZA Wallet bench - frontend logic (vanilla JS, ES2019-safe) */
(function () {
  'use strict';

  // --- DOM handles (own ids only) ---
  var unlockCard = document.getElementById('unlock-card');
  var walletView = document.getElementById('wallet-view');
  var unlockForm = document.getElementById('unlock-form');
  var tokenInput = document.getElementById('token-input');
  var unlockBtn = document.getElementById('unlock-btn');
  var unlockError = document.getElementById('unlock-error');
  var refreshBtn = document.getElementById('refresh-btn');
  var balanceValue = document.getElementById('balance-value');
  var addressText = document.getElementById('address-text');
  var qrImg = document.getElementById('qr-img');
  var copyBtn = document.getElementById('copy-btn');
  var copyFeedback = document.getElementById('copy-feedback');
  var sendTo = document.getElementById('send-to');
  var sendAmount = document.getElementById('send-amount');
  var sendBtn = document.getElementById('send-btn');
  var sendResult = document.getElementById('send-result');
  var txList = document.getElementById('tx-list');
  var txEmpty = document.getElementById('tx-empty');

  var POLL_MS = 15000;
  var pollTimer = null;
  var address = '';

  // Hide brand icons gracefully if the asset is missing (CSP-safe fallback
  // for the icon.png reference; capture phase catches image error events).
  document.addEventListener('error', function (ev) {
    var t = ev.target;
    if (t && t.classList && t.classList.contains('brand-icon')) {
      t.style.display = 'none';
    }
  }, true);

  function api(method, url, body) {
    var opts = {
      method: method,
      headers: {},
      credentials: 'same-origin'
    };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { status: res.status, data: data };
      });
    });
  }

  function setBusy(btn, busy) {
    btn.disabled = busy;
    if (busy) {
      btn.classList.add('busy');
    } else {
      btn.classList.remove('busy');
    }
  }

  function showResult(el, text, ok) {
    el.textContent = text;
    el.hidden = false;
    el.className = 'result-line mono ' + (ok ? 'ok' : 'err');
  }

  function fmtAmount(n) {
    var v = Number(n);
    if (!isFinite(v)) { v = 0; }
    return v.toFixed(8);
  }

  function fmtSigned(n) {
    var v = Number(n);
    if (!isFinite(v)) { v = 0; }
    return (v >= 0 ? '+' : '') + v.toFixed(8);
  }

  function shortTxid(txid) {
    if (txid.length <= 20) { return txid; }
    return txid.slice(0, 10) + '...' + txid.slice(-6);
  }

  function relTime(ts) {
    var now = Math.floor(Date.now() / 1000);
    var s = now - ts;
    if (s < 0) { s = 0; }
    if (s < 60) { return 'just now'; }
    var m = Math.floor(s / 60);
    if (m < 60) { return m + 'm ago'; }
    var h = Math.floor(m / 60);
    if (h < 24) { return h + 'h ago'; }
    var d = Math.floor(h / 24);
    if (d < 30) { return d + 'd ago'; }
    var dt = new Date(ts * 1000);
    return dt.getUTCFullYear() + '-' +
      String(dt.getUTCMonth() + 1).padStart(2, '0') + '-' +
      String(dt.getUTCDate()).padStart(2, '0');
  }

  // --- Views ---

  function showLocked() {
    stopPolling();
    walletView.hidden = true;
    unlockCard.hidden = false;
    unlockError.hidden = true;
    tokenInput.value = '';
    setBusy(unlockBtn, false);
  }

  function showWallet() {
    unlockCard.hidden = true;
    walletView.hidden = false;
    unlockError.hidden = true;
    sendResult.hidden = true;
    copyFeedback.hidden = true;
  }

  // --- State ---

  function loadState() {
    return api('GET', '/api/state').then(function (r) {
      if (r.status === 401) {
        showLocked();
        return;
      }
      if (r.status !== 200) { return; }
      renderState(r.data);
    }).catch(function () { /* network hiccup: keep last state */ });
  }

  function renderState(data) {
    balanceValue.textContent = fmtAmount(data.balance);
    address = String(data.address || '');
    addressText.textContent = address;
    qrImg.src = '/api/qr.svg';
    renderTxs(data.txs || []);
  }

  function renderTxs(txs) {
    txList.textContent = '';
    if (!txs.length) {
      txEmpty.hidden = false;
      return;
    }
    txEmpty.hidden = true;
    txs.forEach(function (tx) {
      var li = document.createElement('li');
      li.className = 'tx-item';

      var arrow = document.createElement('span');
      var incoming = tx.category === 'receive';
      arrow.className = 'tx-arrow ' + (incoming ? 'in' : 'out');
      arrow.textContent = incoming ? '<-' : '->';

      var amount = document.createElement('span');
      amount.className = 'tx-amount';
      amount.textContent = fmtSigned(tx.amount) + ' MAZA';

      var meta = document.createElement('span');
      meta.className = 'tx-meta';
      var confs = Number(tx.confirmations) || 0;
      meta.textContent = confs + ' confs, ' + relTime(Number(tx.time) || 0);

      li.appendChild(arrow);
      li.appendChild(amount);
      li.appendChild(meta);
      txList.appendChild(li);
    });
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(loadState, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // --- Unlock ---

  unlockForm.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var token = tokenInput.value;
    setBusy(unlockBtn, true);
    unlockError.hidden = true;
    api('POST', '/api/unlock', { token: token }).then(function (r) {
      setBusy(unlockBtn, false);
      if (r.status === 401) {
        unlockError.textContent = (r.data && r.data.error) || 'Invalid token.';
        unlockError.hidden = false;
        return;
      }
      if (r.status !== 200) {
        unlockError.textContent = 'Unlock failed. Try again.';
        unlockError.hidden = false;
        return;
      }
      showWallet();
      loadState();
      startPolling();
    }).catch(function () {
      setBusy(unlockBtn, false);
      unlockError.textContent = 'Network error. Try again.';
      unlockError.hidden = false;
    });
  });

  // --- Refresh ---

  refreshBtn.addEventListener('click', function () {
    setBusy(refreshBtn, true);
    loadState().then(function () {
      setBusy(refreshBtn, false);
    });
  });

  // --- Copy address ---

  copyBtn.addEventListener('click', function () {
    function fallbackSelect() {
      var range = document.createRange();
      range.selectNodeContents(addressText);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(address).then(function () {
        copyFeedback.hidden = false;
        setTimeout(function () { copyFeedback.hidden = true; }, 2000);
      }, function () {
        fallbackSelect();
      });
    } else {
      fallbackSelect();
    }
  });

  // --- Send ---

  sendBtn.addEventListener('click', function () {
    var to = sendTo.value.trim();
    var amount = parseFloat(sendAmount.value);
    if (!to) {
      showResult(sendResult, 'Enter a recipient address.', false);
      return;
    }
    if (!isFinite(amount) || amount <= 0) {
      showResult(sendResult, 'Enter a valid amount.', false);
      return;
    }
    setBusy(sendBtn, true);
    sendResult.hidden = true;
    api('POST', '/api/send', { to: to, amount: amount }).then(function (r) {
      setBusy(sendBtn, false);
      if (r.status === 200 && r.data && r.data.txid) {
        showResult(sendResult, 'Sent: ' + shortTxid(r.data.txid), true);
        sendTo.value = '';
        sendAmount.value = '';
        loadState();
      } else {
        var msg = (r.data && r.data.error) || 'Send failed. Try again.';
        showResult(sendResult, msg, false);
      }
    }).catch(function () {
      setBusy(sendBtn, false);
      showResult(sendResult, 'Network error. Try again.', false);
    });
  });

  // --- Boot ---

  showLocked();
})();
