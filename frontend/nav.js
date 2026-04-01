/**
 * nav.js — shared navigation for all Waybound pages.
 *
 * Handles:
 *   - Avatar display (photo or initials)
 *   - Role-aware dropdown (operator vs tourist)
 *   - Operator: bell icon with unread badge fetched async
 *   - toggleNavMenu, navSignOut, outside-click close
 *
 * Include ONCE at the bottom of <body>, after the nav HTML exists.
 * Include after the nav HTML. Old inline IIFEs have been removed from all pages.
 */

// ── Shared nav functions — defined synchronously so pages can call them ──────

function toggleNavMenu() {
  var dropdown = document.getElementById('navDropdown');
  var avatar   = document.getElementById('navAvatar');
  if (!dropdown) return;
  var opening = !dropdown.classList.contains('open');
  dropdown.classList.toggle('open', opening);
  if (avatar) avatar.style.boxShadow = opening ? '0 0 0 3px rgba(255,255,255,.35)' : '';
}

document.addEventListener('click', function (e) {
  var wrap = document.querySelector('.nav-r-wrap');
  if (wrap && !wrap.contains(e.target)) {
    var dd = document.getElementById('navDropdown');
    var av = document.getElementById('navAvatar');
    if (dd) dd.classList.remove('open');
    if (av) av.style.boxShadow = '';
  }
});

function navSignOut() {
  localStorage.removeItem('waybound_access');
  localStorage.removeItem('waybound_refresh');
  localStorage.removeItem('waybound_user');
  window.location.href = 'waybound.html';
}

// ── Language switcher ─────────────────────────────────────────────────────────
function _navCurrentLang() {
  return localStorage.getItem('waybound_lang') || 'en';
}

function _navIsRuPage() {
  return window.location.pathname.endsWith('_ru.html');
}

function navSwitchLang(lang) {
  localStorage.setItem('waybound_lang', lang);
  var path = window.location.pathname;
  var search = window.location.search;
  var isRu = _navIsRuPage();

  // Normalise path: Cloudflare Pages serves extensionless URLs (/adventures),
  // but _ru pages always have the full suffix (_ru.html). Ensure we have .html
  // before doing string replacement.
  var htmlPath = path.endsWith('.html') ? path : path + '.html';

  var target;
  if (lang === 'ru' && !isRu) {
    target = htmlPath.replace('.html', '_ru.html') + search;
  } else if (lang === 'en' && isRu) {
    target = htmlPath.replace('_ru.html', '.html') + search;
  } else {
    return; // already on the right variant
  }
  if (target && target !== path + search) window.location.href = target;
}

// Auto-redirect on page load if saved language doesn't match current page variant.
// Only redirects when the URL contains .html — Cloudflare Pages can serve extensionless
// URLs (/adventures instead of /adventures.html) and a replace() that changes nothing
// would cause an infinite reload loop.
(function () {
  var savedLang = localStorage.getItem('waybound_lang');
  if (!savedLang) return;
  var path = window.location.pathname;
  // Only act on explicit .html paths — skip extensionless, /, index.html, 404.html
  if (!path.endsWith('.html')) return;
  var base = path.split('/').pop();
  if (!base || base === 'index.html' || base === '404.html') return;
  var isRu = _navIsRuPage();
  if (savedLang === 'ru' && !isRu) {
    var ruPath = path.replace('.html', '_ru.html');
    if (ruPath !== path) window.location.replace(ruPath + window.location.search);
  } else if (savedLang === 'en' && isRu) {
    var enPath = path.replace('_ru.html', '.html');
    if (enPath !== path) window.location.replace(enPath + window.location.search);
  }
})();

// Called by operator-dashboard renderMessages() to sync badge after loading enquiries.
function navUpdateMsgBadge(unread) {
  // Bell icon badge
  var bell = document.getElementById('_navBell');
  if (bell) {
    var dot = document.getElementById('_navBellBadge');
    if (unread > 0) {
      if (!dot) {
        dot = document.createElement('span');
        dot.id = '_navBellBadge';
        dot.style.cssText = 'position:absolute;top:-3px;right:-3px;min-width:16px;height:16px;'
          + 'background:#e03030;color:#fff;border-radius:10px;padding:0 3px;box-sizing:border-box;'
          + 'font-size:10px;font-weight:700;font-family:sans-serif;line-height:16px;text-align:center;'
          + 'border:2px solid #1a2535;pointer-events:none;display:block';
        bell.appendChild(dot);
      }
      dot.textContent = unread > 99 ? '99+' : unread;
      dot.style.display = 'block';
    } else {
      if (dot) dot.style.display = 'none';
    }
  }

  // Dropdown Messages link badge
  var link = document.querySelector('[data-nav="messages"]');
  if (!link) return;
  var b = link.querySelector('._navDdBadge');
  if (unread > 0) {
    if (!b) {
      b = document.createElement('span');
      b.className = '_navDdBadge';
      b.style.cssText = 'background:#e03030;color:#fff;border-radius:10px;padding:1px 7px;'
        + 'font-size:10px;font-weight:700;margin-left:4px;font-family:sans-serif';
      link.appendChild(b);
    }
    b.textContent = unread > 99 ? '99+' : unread;
    b.style.display = 'inline-block';
  } else {
    if (b) b.style.display = 'none';
  }
}

function _navInjectLangBtn() {
  var wrap = document.querySelector('.nav-r-wrap');
  if (!wrap || document.getElementById('_navLangBtn')) return;
  var currentLang = _navCurrentLang();
  var langBtn = document.createElement('button');
  langBtn.id = '_navLangBtn';
  langBtn.title = currentLang === 'ru' ? 'Switch to English' : 'Переключить на русский';
  langBtn.textContent = currentLang === 'ru' ? 'EN' : 'RU';
  langBtn.onclick = function (e) {
    e.stopPropagation();
    navSwitchLang(currentLang === 'ru' ? 'en' : 'ru');
  };
  langBtn.style.cssText = 'display:flex;align-items:center;justify-content:center;'
    + 'height:28px;min-width:34px;padding:0 7px;border-radius:5px;border:1px solid rgba(255,255,255,.22);'
    + 'background:rgba(255,255,255,.08);color:rgba(255,255,255,.65);cursor:pointer;'
    + 'font-size:11px;font-weight:700;font-family:var(--bf,"Space Grotesk",sans-serif);'
    + 'letter-spacing:.04em;transition:all .15s;flex-shrink:0';
  langBtn.addEventListener('mouseenter', function () {
    this.style.background = 'rgba(255,255,255,.2)';
    this.style.color = '#fff';
    this.style.borderColor = 'rgba(255,255,255,.4)';
  });
  langBtn.addEventListener('mouseleave', function () {
    this.style.background = 'rgba(255,255,255,.08)';
    this.style.color = 'rgba(255,255,255,.65)';
    this.style.borderColor = 'rgba(255,255,255,.22)';
  });
  wrap.insertBefore(langBtn, wrap.firstChild);
}

// ── Main nav init ─────────────────────────────────────────────────────────────
(function () {
  var API_V1 = window.API_V1 || 'http://127.0.0.1:8000/api/v1';

  var user = null;
  try { user = JSON.parse(localStorage.getItem('waybound_user') || 'null'); } catch (e) {}

  var signInBtn = document.getElementById('navSignInBtn');
  var hamburger = document.getElementById('navHamburger');
  var avatar    = document.getElementById('navAvatar');
  var dropdown  = document.getElementById('navDropdown');

  // ── Language toggle (always visible, logged in or out) ───────────────────
  _navInjectLangBtn();

  if (!user || !user.email) {
    // Logged out — show sign-in, hide avatar + bell
    if (signInBtn) signInBtn.style.display = '';
    if (hamburger) hamburger.style.display = 'none';
    if (avatar)    avatar.style.display    = 'none';
    if (dropdown)  dropdown.innerHTML      = '';
    var oldBell = document.getElementById('_navBell');
    if (oldBell) oldBell.style.display = 'none';
    return;
  }

  // ── Logged in ─────────────────────────────────────────────────────────────
  if (signInBtn) signInBtn.style.display = 'none';
  if (hamburger) hamburger.style.display = 'none';
  if (avatar)    avatar.style.display    = 'flex';

  var fullName = ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || user.email;
  var initials = fullName.split(' ').filter(Boolean).map(function (w) { return w[0]; }).join('').toUpperCase().slice(0, 2);

  if (avatar) {
    if (user.photo_url) {
      avatar.innerHTML = '<img src="' + user.photo_url + '" alt="' + initials
        + '" style="width:100%;height:100%;object-fit:cover;border-radius:50%">';
    } else {
      avatar.textContent = initials;
    }
  }

  var isOp = user.role === 'operator';

  // ── Bell icon (operators only) ────────────────────────────────────────────
  if (isOp) {
    var wrap = document.querySelector('.nav-r-wrap');
    if (wrap && !document.getElementById('_navBell')) {
      var bell = document.createElement('button');
      bell.id = '_navBell';
      bell.title = 'Messages';
      bell.onclick = function (e) {
        e.stopPropagation();
        var sfx = _navIsRuPage() ? '_ru.html' : '.html';
        window.location.href = 'operator-dashboard' + sfx + '?tab=messages';
      };
      bell.style.cssText = 'position:relative;display:flex;align-items:center;justify-content:center;'
        + 'width:36px;height:36px;border-radius:50%;border:none;'
        + 'background:rgba(255,255,255,.12);color:#fff;cursor:pointer;'
        + 'font-size:17px;transition:background .18s;flex-shrink:0;padding:0';
      bell.innerHTML = '&#x1F514;';
      bell.addEventListener('mouseenter', function () { this.style.background = 'rgba(255,255,255,.25)'; });
      bell.addEventListener('mouseleave', function () { this.style.background = 'rgba(255,255,255,.12)'; });
      // Insert before avatar so order is: [bell] [avatar▾]
      wrap.insertBefore(bell, avatar);
    }
  }

  // ── Dropdown builder ──────────────────────────────────────────────────────
  function buildDropdown(unread) {
    if (!dropdown) return;

    var isRu = _navIsRuPage();
    var sfx  = isRu ? '_ru.html' : '.html';

    var badge = unread > 0
      ? ' <span class="_navDdBadge" style="background:#e03030;color:#fff;border-radius:10px;padding:1px 7px;'
        + 'font-size:10px;font-weight:700;margin-left:4px;font-family:sans-serif">' + unread + '</span>'
      : '';

    var t = isRu ? {
      dashboard: 'Дашборд', messages: 'Сообщения', newTour: 'Новый тур',
      myBookings: 'Мои бронирования', savedTours: 'Сохранённые туры',
      myReviews: 'Мои отзывы', rewards: 'Бонусы',
      settings: 'Настройки', signOut: 'Выйти'
    } : {
      dashboard: 'Dashboard', messages: 'Messages', newTour: 'New tour',
      myBookings: 'My bookings', savedTours: 'Saved tours',
      myReviews: 'My reviews', rewards: 'Rewards',
      settings: 'Settings', signOut: 'Sign out'
    };

    var opLinks =
      '<a class="nav-dd-item" href="operator-dashboard' + sfx + '"><span class="dd-ico">&#x1F4CA;</span>' + t.dashboard + '</a>'
      + '<a class="nav-dd-item" data-nav="messages" href="operator-dashboard' + sfx + '?tab=messages">'
          + '<span class="dd-ico">&#x1F4AC;</span>' + t.messages + badge + '</a>'
      + '<a class="nav-dd-item" href="operator-tour-create' + sfx + '"><span class="dd-ico">&#x2795;</span>' + t.newTour + '</a>';

    var touristLinks =
      '<a class="nav-dd-item" href="my-bookings' + sfx + '"><span class="dd-ico">&#x1F9ED;</span>' + t.myBookings + '</a>'
      + '<a class="nav-dd-item" href="my-messages' + sfx + '"><span class="dd-ico">&#x1F4AC;</span>' + t.messages + '</a>'
      + '<a class="nav-dd-item" href="saved-tours' + sfx + '"><span class="dd-ico">&#x2764;&#xFE0F;</span>' + t.savedTours + '</a>'
      + '<a class="nav-dd-item" href="my-reviews' + sfx + '"><span class="dd-ico">&#x2B50;</span>' + t.myReviews + '</a>'
      + '<a class="nav-dd-item" href="rewards' + sfx + '"><span class="dd-ico">&#x1F3C6;</span>' + t.rewards + '</a>';

    dropdown.innerHTML =
      '<div class="nav-dropdown-head">'
        + '<div class="nav-dropdown-name">' + fullName + '</div>'
        + '<div class="nav-dropdown-email">' + (user.email || '') + '</div>'
      + '</div>'
      + (isOp ? opLinks : touristLinks)
      + '<div class="nav-dd-sep"></div>'
      + '<a class="nav-dd-item" href="settings' + sfx + '"><span class="dd-ico">&#x2699;&#xFE0F;</span>' + t.settings + '</a>'
      + '<div class="nav-dd-sep"></div>'
      + '<div class="nav-dd-item dd-danger" onclick="navSignOut()"><span class="dd-ico">&#x1F6AA;</span>' + t.signOut + '</div>';
  }

  // Build dropdown immediately (instant feel, no count yet)
  buildDropdown(0);

  // Async: fetch unread count for operators → update bell + dropdown badge
  if (isOp) {
    var tok = localStorage.getItem('waybound_access');
    if (tok) {
      fetch(API_V1 + '/bookings/enquiries/?unread=1', {
        headers: { 'Authorization': 'Bearer ' + tok }
      })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          var count = (d && d.count) || 0;
          if (count > 0) {
            buildDropdown(count);
            navUpdateMsgBadge(count);
          }
        })
        .catch(function () {});
      // Poll bell badge every 30 s while page is open
      var _bellPoll = setInterval(function () {
        var freshTok = localStorage.getItem('waybound_access');
        if (!freshTok) { clearInterval(_bellPoll); return; }
        fetch(API_V1 + '/bookings/enquiries/?unread=1', {
          headers: { 'Authorization': 'Bearer ' + freshTok }
        })
          .then(function (r) {
            if (r.status === 401) { clearInterval(_bellPoll); return null; }
            return r.ok ? r.json() : null;
          })
          .then(function (d) { if (d) navUpdateMsgBadge((d && d.count) || 0); })
          .catch(function () {});
      }, 30000);
    }
  }
  // Tourist unread: needs tourist_read_at field on EnquiryMessage (future task).
  // Messages link shown without count for now.
})();
