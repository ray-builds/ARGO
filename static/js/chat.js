// ═══════════════════════════════════════════
// ARGO — AI Assistant Chat Interface
// ARP Global Capital
// ═══════════════════════════════════════════

let currentConversationId = null;

// ─── Init ─────────────────────────────────

function initChat() {
  const input = document.getElementById('chat-input');
  const form  = document.getElementById('chat-form');

  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (!input) return;
      const message = input.value.trim();
      if (!message) return;
      input.value = '';
      autoResizeTextarea(input);
      await sendMessage(message);
    });
  }

  // Enter (without Shift) submits; Shift+Enter adds newline
  if (input) {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const submitForm = document.getElementById('chat-form');
        if (submitForm) submitForm.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    // Auto-resize textarea as user types
    input.addEventListener('input', function () {
      autoResizeTextarea(input);
    });
  }

  // Scroll to bottom of messages on load
  scrollChatToBottom();
}

// ─── Auto-resize textarea ─────────────────

function autoResizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// ─── Append a message bubble ──────────────

/**
 * @param {'user'|'assistant'|'system'} role
 * @param {string} content  Plain text (will be escaped)
 * @returns {HTMLElement} The created message element
 */
function appendMessage(role, content) {
  const container = document.getElementById('chat-messages');
  if (!container) return null;

  const wrapper = document.createElement('div');
  wrapper.className = `chat-message chat-message-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  // Render markdown-like newlines as <br>
  bubble.innerHTML = escapeHtml(content).replace(/\n/g, '<br>');

  wrapper.appendChild(bubble);
  container.appendChild(wrapper);
  scrollChatToBottom();
  return wrapper;
}

// ─── Send Message ─────────────────────────

async function sendMessage(message) {
  appendMessage('user', message);
  disableChatInput(true);

  // Thinking indicator
  const thinkingEl = document.createElement('div');
  thinkingEl.className = 'chat-message chat-message-assistant thinking';
  thinkingEl.id = 'argo-thinking';
  thinkingEl.innerHTML = '<div class="chat-bubble">ARGO is thinking...</div>';
  const container = document.getElementById('chat-messages');
  if (container) {
    container.appendChild(thinkingEl);
    scrollChatToBottom();
  }

  try {
    let data;

    if (!currentConversationId) {
      // Start a new conversation
      data = await argoFetch('/api/v1/assistant/conversations', {
        method: 'POST',
        body: JSON.stringify({ first_message: message }),
      });
      currentConversationId = data.conversation_id;

      // Update conversation list sidebar if present
      addConversationToSidebar(currentConversationId, message);
    } else {
      // Continue existing conversation
      data = await argoFetch(
        `/api/v1/assistant/conversations/${currentConversationId}/messages`,
        {
          method: 'POST',
          body: JSON.stringify({ content: message }),
        },
      );
    }

    thinkingEl.remove();
    appendMessage('assistant', data.reply || data.content || '(no response)');
  } catch (_) {
    thinkingEl.remove();
    appendMessage('assistant', 'Sorry, something went wrong. Please try again.');
  } finally {
    disableChatInput(false);
  }
}

// ─── New Conversation ─────────────────────

function startNewConversation() {
  currentConversationId = null;
  const container = document.getElementById('chat-messages');
  if (container) container.innerHTML = '';

  // Deactivate sidebar items
  document.querySelectorAll('.conversation-item').forEach(function (el) {
    el.classList.remove('active');
  });

  // Show suggested prompts again if they exist
  const prompts = document.getElementById('suggested-prompts');
  if (prompts) prompts.style.display = 'block';

  // Focus input
  const input = document.getElementById('chat-input');
  if (input) input.focus();
}

// ─── Load Existing Conversation ───────────

async function loadConversation(conversationId) {
  if (conversationId === currentConversationId) return;

  currentConversationId = conversationId;

  // Highlight sidebar item
  document.querySelectorAll('.conversation-item').forEach(function (el) {
    el.classList.toggle('active', el.dataset.conversationId === conversationId);
  });

  const container = document.getElementById('chat-messages');
  if (!container) return;

  container.innerHTML = '<div class="loading-overlay"><div class="loading-spinner"></div> Loading...</div>';

  try {
    const data = await argoFetch(`/api/v1/assistant/conversations/${conversationId}`);
    container.innerHTML = '';

    const prompts = document.getElementById('suggested-prompts');
    if (prompts) prompts.style.display = 'none';

    (data.messages || []).forEach(function (msg) {
      appendMessage(msg.role, msg.content);
    });
  } catch (_) {
    container.innerHTML = '';
  }
}

// ─── Add Conversation to Sidebar ─────────

function addConversationToSidebar(conversationId, firstMessage) {
  const sidebar = document.getElementById('conversation-list');
  if (!sidebar) return;

  // Deactivate others
  sidebar.querySelectorAll('.conversation-item').forEach(function (el) {
    el.classList.remove('active');
  });

  const item = document.createElement('div');
  item.className = 'conversation-item active';
  item.dataset.conversationId = conversationId;
  item.textContent = firstMessage.substring(0, 60) + (firstMessage.length > 60 ? '…' : '');
  item.onclick = function () { loadConversation(conversationId); };

  sidebar.insertBefore(item, sidebar.firstChild);
}

// ─── Suggested Prompt ─────────────────────

function useSuggestedPrompt(text) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = text;
    input.focus();
    autoResizeTextarea(input);
  }
}

// ─── Helpers ──────────────────────────────

function scrollChatToBottom() {
  const container = document.getElementById('chat-messages');
  if (container) container.scrollTop = container.scrollHeight;
}

function disableChatInput(disabled) {
  const input  = document.getElementById('chat-input');
  const submit = document.getElementById('chat-submit-btn');
  if (input)  input.disabled  = disabled;
  if (submit) submit.disabled = disabled;
}

/**
 * Escape HTML special characters to prevent XSS.
 *
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ─── Bootstrap ────────────────────────────

document.addEventListener('DOMContentLoaded', initChat);
