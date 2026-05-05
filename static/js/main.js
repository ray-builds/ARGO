// ═══════════════════════════════════════════
// ARGO — Global JavaScript Utilities
// ARP Global Capital
// ═══════════════════════════════════════════

// Flash message auto-dismiss
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert[data-auto-dismiss]');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.opacity = '0';
      alert.style.transition = 'opacity 0.5s';
      setTimeout(function () { alert.remove(); }, 500);
    }, 4000);
  });
});

// ─── Modal Utilities ──────────────────────

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Close modal on overlay click
document.addEventListener('click', function (e) {
  if (e.target.classList.contains('modal-overlay')) {
    const modal = e.target.closest('.modal');
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  }
});

// Close modal on Escape key
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal.active').forEach(function (modal) {
      modal.classList.remove('active');
    });
    document.body.style.overflow = '';
  }
});

// ─── API Fetch Wrapper ────────────────────

/**
 * Generic fetch wrapper for the ARGO API.
 * Handles JSON encoding, error normalisation, and toast notifications.
 *
 * @param {string} url
 * @param {RequestInit} options
 * @returns {Promise<any>} Parsed JSON response
 */
async function argoFetch(url, options = {}) {
  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      let errDetail = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        errDetail = err.detail || err.message || errDetail;
      } catch (_) {}
      throw new Error(errDetail);
    }

    return await response.json();
  } catch (err) {
    console.error('ARGO fetch error:', err);
    showToast(err.message || 'Request failed', 'error');
    throw err;
  }
}

// ─── Toast Notifications ──────────────────

/**
 * Show a temporary toast notification.
 *
 * @param {string} message
 * @param {'info'|'success'|'error'|'warning'} type
 * @param {number} duration  ms before auto-dismiss (default 4000)
 */
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container') || createToastContainer();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = 'opacity:1; transition: opacity 0.4s;';

  container.appendChild(toast);

  // Auto-dismiss
  setTimeout(function () {
    toast.style.opacity = '0';
    setTimeout(function () { toast.remove(); }, 400);
  }, duration);
}

function createToastContainer() {
  const el = document.createElement('div');
  el.id = 'toast-container';
  el.style.cssText = [
    'position: fixed',
    'bottom: 24px',
    'right: 24px',
    'z-index: 9999',
    'display: flex',
    'flex-direction: column',
    'gap: 8px',
    'pointer-events: none',
  ].join(';');
  document.body.appendChild(el);
  return el;
}

// ─── Confirm Helper ───────────────────────

/**
 * Show a native confirm dialog; execute callback only if confirmed.
 *
 * @param {string} message
 * @param {Function} callback
 */
function confirmAction(message, callback) {
  if (window.confirm(message)) {
    callback();
  }
}

// ─── Relative Time ────────────────────────

/**
 * Format an ISO 8601 string as human-readable relative time.
 *
 * @param {string} isoString
 * @returns {string}
 */
function formatRelativeTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1)  return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ─── Tab Panel Helper ─────────────────────

/**
 * Activate a tab panel by panel ID.
 *
 * @param {string} panelId
 * @param {HTMLElement|null} clickedBtn
 */
function activateTab(panelId, clickedBtn) {
  // Deactivate all tabs in the same nav
  if (clickedBtn) {
    const nav = clickedBtn.closest('.tab-nav');
    if (nav) {
      nav.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.classList.remove('active');
      });
    }
    clickedBtn.classList.add('active');
  }

  // Switch panels
  const container = document.querySelector('.tab-panels');
  if (container) {
    container.querySelectorAll('.tab-panel').forEach(function (panel) {
      panel.classList.remove('active');
    });
  }

  const target = document.getElementById(panelId);
  if (target) target.classList.add('active');
}

// ─── Copy to Clipboard ────────────────────

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('Copied to clipboard', 'success', 2000);
  } catch (_) {
    showToast('Copy failed', 'error');
  }
}

// ─── Debounce ─────────────────────────────

/**
 * Returns a debounced version of the given function.
 *
 * @param {Function} fn
 * @param {number} delay ms
 */
function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// ─── Number Formatting ────────────────────

function formatCurrency(value, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    notation: Math.abs(value) >= 1e6 ? 'compact' : 'standard',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value, decimals = 2) {
  return `${(value * 100).toFixed(decimals)}%`;
}

// ─── Score Badge Helper ───────────────────

/**
 * Return CSS class suffix for a relevance score.
 *
 * @param {number} score  0–100
 * @returns {'critical'|'high'|'medium'|'low'}
 */
function scoreClass(score) {
  if (score >= 90) return 'critical';
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}
