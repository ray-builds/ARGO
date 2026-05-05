// ═══════════════════════════════════════════
// ARGO — Email Intelligence Module
// ARP Global Capital
// ═══════════════════════════════════════════

// ─── Tag Filter ───────────────────────────

/**
 * Filter email cards by tag.
 *
 * @param {string} tag  Tag name or 'ALL'
 */
function filterByTag(tag) {
  const cards = document.querySelectorAll('.email-card');
  const btns  = document.querySelectorAll('.tag-filter-btn');

  // Toggle active button
  btns.forEach(function (btn) { btn.classList.remove('active'); });
  const activeBtn = document.querySelector(`.tag-filter-btn[data-tag="${tag}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  // Show / hide cards
  cards.forEach(function (card) {
    const show = tag === 'ALL' || card.dataset.tag === tag;
    card.style.display = show ? 'block' : 'none';
  });

  // Update visible count
  const visible = document.querySelectorAll('.email-card[style="display: block;"], .email-card:not([style*="none"])').length;
  const countEl = document.getElementById('inbox-visible-count');
  if (countEl) countEl.textContent = tag === 'ALL' ? 'All' : tag;
}

// ─── Archive Single Email ─────────────────

/**
 * Archive a single email by ID after confirmation.
 *
 * @param {string} emailId
 */
async function archiveEmail(emailId) {
  confirmAction('Archive this email?', async function () {
    try {
      await argoFetch(`/api/v1/email/${emailId}/archive`, { method: 'POST' });
      const card = document.getElementById(`email-card-${emailId}`);
      if (card) {
        card.style.transition = 'opacity 0.3s, max-height 0.3s';
        card.style.opacity = '0';
        setTimeout(function () { card.remove(); }, 300);
      }
      showToast('Email archived', 'success');
    } catch (_) {
      // Error shown by argoFetch
    }
  });
}

// ─── Archive All SKIP emails ──────────────

/**
 * Bulk-archive all emails tagged SKIP.
 */
async function archiveAllSkip() {
  const skipCards = document.querySelectorAll('.email-card[data-tag="SKIP"]');
  const ids = Array.from(skipCards).map(function (c) { return c.dataset.emailId; });

  if (!ids.length) {
    showToast('No SKIP emails to archive', 'info');
    return;
  }

  confirmAction(`Archive ${ids.length} SKIP email(s)? This cannot be undone.`, async function () {
    try {
      const result = await argoFetch('/api/v1/email/archive-bulk', {
        method: 'POST',
        body: JSON.stringify({ email_ids: ids }),
      });

      skipCards.forEach(function (card) {
        card.style.transition = 'opacity 0.3s';
        card.style.opacity = '0';
        setTimeout(function () { card.remove(); }, 300);
      });

      showToast(`Archived ${result.archived} email(s)`, 'success');
    } catch (_) {}
  });
}

// ─── Fetch / Refresh Emails ───────────────

/**
 * Trigger a fresh fetch of emails from Microsoft Graph.
 *
 * @param {string} userEmail  Microsoft 365 email address
 */
async function fetchEmails(userEmail) {
  const btn = document.getElementById('fetch-emails-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Fetching...';
  }

  try {
    const result = await argoFetch('/api/v1/email/fetch', {
      method: 'POST',
      body: JSON.stringify({ user_email: userEmail, force_refresh: false }),
    });

    const newCount = result.new || 0;
    showToast(
      newCount > 0 ? `Fetched ${newCount} new email(s)` : 'Inbox is up to date',
      'success',
    );

    if (newCount > 0) {
      setTimeout(function () { location.reload(); }, 1200);
    }
  } catch (_) {
    // Error already shown by argoFetch
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Refresh';
    }
  }
}

// ─── Mark Email Read ──────────────────────

async function markEmailRead(emailId) {
  try {
    await argoFetch(`/api/v1/email/${emailId}/read`, { method: 'POST' });
    const card = document.getElementById(`email-card-${emailId}`);
    if (card) card.classList.remove('email-card-unread');
  } catch (_) {}
}

// ─── Update Tag ───────────────────────────

async function updateEmailTag(emailId, newTag) {
  try {
    await argoFetch(`/api/v1/email/${emailId}/tag`, {
      method: 'PATCH',
      body: JSON.stringify({ tag: newTag }),
    });
    showToast(`Tag updated to ${newTag}`, 'success');
  } catch (_) {}
}

// ─── Render score badge ───────────────────

/**
 * Build a score badge HTML string.
 *
 * @param {number} score
 * @returns {string}
 */
function renderScoreBadge(score) {
  const cls = scoreClass(score);
  return `<span class="score-badge score-badge-${cls}">${score}</span>`;
}

// ─── Render tag badge ─────────────────────

/**
 * Build a tag badge HTML string.
 *
 * @param {string} tag
 * @returns {string}
 */
function renderTagBadge(tag) {
  const t = (tag || 'SKIP').toLowerCase();
  return `<span class="badge tag-badge-${t}">${tag || 'SKIP'}</span>`;
}
