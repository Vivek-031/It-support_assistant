const API_BASE = '/api';
const MIN_LENGTH = 10;
const MAX_LENGTH = 1000;
const REQUEST_TIMEOUT_MS = 60000;

const $ = (id) => document.getElementById(id);
const els = {
  status: $('status'),
  form: $('ask-form'),
  question: $('question'),
  charCount: $('char-count'),
  submit: $('submit-btn'),
  formError: $('form-error'),
  result: $('result'),
  loading: $('loading'),
  errorBox: $('error-box'),
  answer: $('answer'),
  ticketMeta: $('ticket-meta'),
  ticketQuestion: $('ticket-question'),
  answerText: $('answer-text'),
  sources: $('sources'),
  ticketList: $('ticket-list'),
  refresh: $('refresh-btn'),
};

let activeTicketId = null;

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(API_BASE + path, {
      ...options,
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const error = new Error(errorMessage(body, res.status));
      error.ticketId = body?.detail?.ticket_id;
      throw error;
    }
    return body;
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('The request timed out. Please try again.');
    if (err instanceof TypeError) throw new Error('Cannot reach the server. Is the backend running?');
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function errorMessage(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg.replace(/^Value error, /, '')).join(' ');
  if (detail?.message) return detail.message;
  return `Request failed (HTTP ${status}).`;
}

function validateQuestion(text) {
  if (text.length < MIN_LENGTH) return `Please describe the problem in at least ${MIN_LENGTH} characters.`;
  if (text.length > MAX_LENGTH) return `Please keep it under ${MAX_LENGTH} characters.`;
  if (!/[A-Za-z]{2,}/.test(text)) return 'Please describe the problem in words.';
  return null;
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Escape first, then allow only **bold** so model output can never inject HTML.
function renderAnswer(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^#{1,6}\s*(.+)$/gm, '<strong>$1</strong>');
}

function setLoading(isLoading) {
  els.submit.disabled = isLoading;
  els.submit.textContent = isLoading ? 'Working…' : 'Get help';
  els.question.readOnly = isLoading;
  if (isLoading) {
    els.result.hidden = false;
    els.answer.hidden = true;
    els.errorBox.hidden = true;
  }
  els.loading.hidden = !isLoading;
}

function showError(message) {
  els.result.hidden = false;
  els.answer.hidden = true;
  els.errorBox.textContent = message;
  els.errorBox.hidden = false;
}

function showTicket(ticket) {
  activeTicketId = ticket.id;
  els.result.hidden = false;
  els.ticketQuestion.textContent = ticket.question;
  els.ticketMeta.textContent = `Ticket #${ticket.id} · ${new Date(ticket.created_at).toLocaleString()}`;

  if (ticket.status === 'failed' || !ticket.ai_response) {
    els.answer.hidden = true;
    showError(`Ticket #${ticket.id} has no AI answer: ${ticket.error_message || 'still open.'}`);
  } else {
    els.errorBox.hidden = true;
    els.answerText.innerHTML = renderAnswer(ticket.ai_response);
    els.answer.hidden = false;
  }

  els.sources.replaceChildren();
  if (ticket.sources.length === 0) {
    const li = document.createElement('li');
    li.className = 'muted';
    li.textContent = 'No matching articles; the answer is general guidance.';
    els.sources.append(li);
  }
  for (const source of ticket.sources) {
    const li = document.createElement('li');
    const title = document.createElement('span');
    title.textContent = `[KB-${source.id}] ${source.title}`;
    const meta = document.createElement('span');
    meta.className = 'muted';
    meta.textContent = `${source.category} · score ${source.score.toFixed(2)}`;
    li.append(title, meta);
    els.sources.append(li);
  }
  highlightActiveTicket();
}

function highlightActiveTicket() {
  for (const btn of els.ticketList.querySelectorAll('button')) {
    btn.classList.toggle('active', Number(btn.dataset.id) === activeTicketId);
  }
}

async function loadTickets() {
  try {
    const tickets = await api('/tickets?limit=20');
    els.ticketList.replaceChildren();
    if (tickets.length === 0) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = 'No tickets yet.';
      els.ticketList.append(li);
      return;
    }
    for (const t of tickets) {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.id = t.id;

      const head = document.createElement('span');
      head.className = 'muted';
      head.textContent = `#${t.id}`;
      const badge = document.createElement('span');
      badge.className = `badge ${t.status}`;
      badge.textContent = t.status;
      head.append(badge);

      const q = document.createElement('span');
      q.className = 'q';
      q.textContent = t.question;

      btn.append(head, q);
      btn.addEventListener('click', () => openTicket(t.id));
      li.append(btn);
      els.ticketList.append(li);
    }
    highlightActiveTicket();
  } catch (err) {
    els.ticketList.replaceChildren();
    const li = document.createElement('li');
    li.className = 'field-error';
    li.textContent = `Could not load tickets: ${err.message}`;
    els.ticketList.append(li);
  }
}

async function openTicket(id) {
  try {
    showTicket(await api(`/tickets/${id}`));
  } catch (err) {
    showError(err.message);
  }
}

async function checkHealth() {
  try {
    const health = await api('/health');
    if (health.llm_configured) {
      els.status.textContent = `AI ready · ${health.llm_provider}`;
      els.status.className = 'pill ok';
    } else {
      els.status.textContent = `API key missing (${health.llm_provider})`;
      els.status.className = 'pill warn';
    }
  } catch {
    els.status.textContent = 'Backend offline';
    els.status.className = 'pill err';
  }
}

function updateCharCount() {
  els.charCount.textContent = `${els.question.value.length} / ${MAX_LENGTH}`;
}

els.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (els.submit.disabled) return;

  const question = els.question.value.trim().replace(/\s+/g, ' ');
  const problem = validateQuestion(question);
  els.formError.textContent = problem || '';
  els.formError.hidden = !problem;
  if (problem) return;

  setLoading(true);
  try {
    const ticket = await api('/tickets', {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
    showTicket(ticket);
    els.question.value = '';
    updateCharCount();
  } catch (err) {
    const suffix = err.ticketId ? ` (saved as ticket #${err.ticketId})` : '';
    showError(err.message + suffix);
  } finally {
    setLoading(false);
    loadTickets();
  }
});

els.question.addEventListener('input', () => {
  updateCharCount();
  els.formError.hidden = true;
});

els.question.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) els.form.requestSubmit();
});

for (const chip of document.querySelectorAll('.chip')) {
  chip.addEventListener('click', () => {
    els.question.value = chip.textContent;
    updateCharCount();
    els.question.focus();
  });
}

els.refresh.addEventListener('click', loadTickets);

checkHealth();
loadTickets();
