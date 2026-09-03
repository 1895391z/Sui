const chat = document.querySelector('#chat');
const form = document.querySelector('#composer');
const input = document.querySelector('#input');
const send = document.querySelector('#send');
const dryRun = document.querySelector('#dryRun');
const health = document.querySelector('.health');
const healthText = document.querySelector('#healthText');
const conversationId = (self.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9_-]/g, '');

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function appendMessage(role, text, data = null) {
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const avatar = role === 'user' ? '我' : 'AI';
  let extras = '';
  if (data?.model_warning) extras += `<div class="warning">${escapeHtml(data.model_warning)}</div>`;
  if (data?.interpreted_request) extras += `<div class="interpreted">已结合上一轮理解为：${escapeHtml(data.interpreted_request)}</div>`;
  if (data?.result) {
    extras += `<div class="result-tools"><details><summary>查看完整仿真 JSON</summary><pre>${escapeHtml(JSON.stringify(data.result, null, 2))}</pre></details></div>`;
  }
  article.innerHTML = `<div class="avatar">${avatar}</div><div class="bubble"><p>${escapeHtml(text)}</p>${extras}</div>`;
  chat.appendChild(article);
  window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});
  return article;
}

function appendLoading(isDryRun) {
  const article = document.createElement('article');
  article.className = 'message assistant';
  article.innerHTML = `<div class="avatar">AI</div><div class="bubble"><p>${isDryRun ? '正在解析并校验参数…' : '正在启动 HYSYS 并执行仿真，这可能需要几分钟…'}</p><span class="typing"><i></i><i></i><i></i></span></div>`;
  chat.appendChild(article);
  window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});
  return article;
}

async function submit() {
  const message = input.value.trim();
  if (!message || send.disabled) return;
  appendMessage('user', message);
  input.value = '';
  resize();
  send.disabled = true;
  const loading = appendLoading(dryRun.checked);
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message, dry_run: dryRun.checked, conversation_id: conversationId})
    });
    const data = await response.json();
    loading.remove();
    if (!response.ok) throw new Error(data.error || '请求失败');
    appendMessage('assistant', data.answer, data);
  } catch (error) {
    loading.remove();
    appendMessage('assistant', `请求失败：${error.message}`);
  } finally {
    send.disabled = false;
    input.focus();
  }
}

function resize() { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 180)}px`; }
form.addEventListener('submit', event => { event.preventDefault(); submit(); });
input.addEventListener('input', resize);
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); }
});
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => {
  input.value = button.dataset.prompt; resize(); input.focus();
}));

fetch('/api/health').then(r => r.json()).then(data => {
  health.classList.add('online');
  healthText.textContent = data.model_enabled ? `已连接 · ${data.model}` : '本地模式 · 未配置大模型';
}).catch(() => {
  health.classList.add('offline'); healthText.textContent = '服务未连接';
});
