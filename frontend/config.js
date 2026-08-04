/**
 * Kavkazland frontend configuration.
 * Change API_BASE here once — all pages pick it up.
 *
 * For local dev:  http://127.0.0.1:8000
 * For production: https://api.kavkazland.com  (or wherever your Django server lives)
 */
// DEV: http://127.0.0.1:8000
// PRODUCTION: api.kavkazland.com — a Cloudflare-proxied CNAME to the Railway
// service. Prefer this over the raw *.up.railway.app host: some ISPs refuse to
// resolve that domain, which makes the site look down to their customers.
var _API_BASE = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
  ? 'http://127.0.0.1:8000'
  : 'https://api.kavkazland.com';

window.WAYBOUND_CONFIG = {
  API_BASE: _API_BASE,
  API_V1:   _API_BASE + '/api/v1',
};

// Convenience shortcuts used throughout the codebase
window.API_BASE = window.WAYBOUND_CONFIG.API_BASE;
window.API_V1   = window.WAYBOUND_CONFIG.API_V1;
