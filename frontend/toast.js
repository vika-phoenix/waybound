// Waybound toast notification system
(function() {
  var container;
  function getContainer() {
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none;';
      document.body.appendChild(container);
    }
    return container;
  }
  window.showToast = function(msg, type, duration) {
    type = type || 'info'; // 'success', 'error', 'info', 'warning'
    duration = duration || 3500;
    var colors = { success: '#2ecc71', error: '#e74c3c', info: '#3498db', warning: '#f39c12' };
    var icons  = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
    var t = document.createElement('div');
    t.style.cssText = 'background:#1a2a3a;color:#fff;padding:12px 18px;border-radius:8px;font-size:13.5px;font-family:var(--bf,"sans-serif");display:flex;align-items:center;gap:10px;pointer-events:auto;box-shadow:0 4px 16px rgba(0,0,0,.25);max-width:320px;opacity:0;transform:translateY(10px);transition:opacity .2s,transform .2s;';
    t.innerHTML = '<span style="width:20px;height:20px;border-radius:50%;background:' + colors[type] + ';display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">' + icons[type] + '</span><span>' + msg + '</span>';
    getContainer().appendChild(t);
    requestAnimationFrame(function(){ t.style.opacity='1'; t.style.transform='translateY(0)'; });
    setTimeout(function(){
      t.style.opacity='0'; t.style.transform='translateY(10px)';
      setTimeout(function(){ if(t.parentNode) t.parentNode.removeChild(t); }, 250);
    }, duration);
  };
})();
