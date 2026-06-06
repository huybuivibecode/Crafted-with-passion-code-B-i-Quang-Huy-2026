/**
 * BurgerPrintsAgent - Frontend Chat Logic
 * Handles chat UI, API calls, product cards rendering
 */

// ─── State ──────────────────────────────────────────────────────────────────
const state = {
  sessionId: document.getElementById('session-id-input')?.value || crypto.randomUUID(),
  isLoading: false,
  activeFilters: {
    location: '',
    print: '',
    lead: '999',
  },
  allProducts: [],
};

// ─── DOM Elements ────────────────────────────────────────────────────────────
const messagesContainer = document.getElementById('messages-container');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const charCount = document.getElementById('char-count');
const productCardsArea = document.getElementById('product-cards-area');
const productCardsGrid = document.getElementById('product-cards-grid');
const productCardsTitle = document.getElementById('product-cards-title');
const productCount = document.getElementById('product-count');
const statusIndicator = document.getElementById('status-indicator');
const statusLabel = document.getElementById('status-label');
const toast = document.getElementById('toast');
const btnNewChat = document.getElementById('btn-new-chat');

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  checkAPIStatus();
  autoResizeTextarea();
});

function setupEventListeners() {
  // Send button
  sendBtn?.addEventListener('click', handleSend);

  // Enter to send, Shift+Enter for newline
  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Char count
  chatInput?.addEventListener('input', () => {
    const len = chatInput.value.length;
    charCount.textContent = `${len}/500`;
    charCount.style.color = len > 450 ? '#EF4444' : 'var(--text-muted)';
    autoResizeTextarea();
  });

  // Quick prompts
  document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const prompt = btn.dataset.prompt;
      chatInput.value = prompt;
      chatInput.dispatchEvent(new Event('input'));
      chatInput.focus();
      handleSend();
    });
  });

  // Filter tags
  document.querySelectorAll('.filter-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const filterType = tag.dataset.filter;
      const filterValue = tag.dataset.value;

      // Update active state in group
      document.querySelectorAll(`.filter-tag[data-filter="${filterType}"]`).forEach(t => {
        t.classList.remove('active');
      });
      tag.classList.add('active');

      state.activeFilters[filterType] = filterValue;
      applyFilters();
    });
  });

  // New chat button
  btnNewChat?.addEventListener('click', () => {
    state.sessionId = crypto.randomUUID();
    document.getElementById('session-display').textContent = state.sessionId.substring(0, 12) + '...';
    clearChat();
    showToast('Đã tạo phiên chat mới', 'info');
  });
}

// ─── Auto-resize textarea ──────────────────────────────────────────────────
function autoResizeTextarea() {
  if (!chatInput) return;
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
}

// ─── Send message ─────────────────────────────────────────────────────────────
async function handleSend() {
  const query = chatInput?.value?.trim();
  if (!query || state.isLoading) return;

  // Clear input
  chatInput.value = '';
  chatInput.style.height = 'auto';
  charCount.textContent = '0/500';

  // Show user message
  appendUserMessage(query);

  // Show typing indicator with loading note
  const loadingNote = getLoadingText(query);
  const typingId = showTypingIndicator(loadingNote);

  // Disable input while loading
  setLoading(true);

  try {
    const response = await fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({
        query: query,
        session_id: state.sessionId,
      }),
    });

    const data = await response.json();

    // Remove typing indicator
    removeTypingIndicator(typingId);

    if (data.error && !data.response) {
      appendAssistantMessage(`❌ ${data.error}`, 'error');
    } else {
      // Show assistant response
      appendAssistantMessage(data.response || 'Xin lỗi, tôi không có câu trả lời.', data.intent);

      // Show product cards if available
      if (data.products && data.products.length > 0) {
        state.allProducts = data.products;
        showProductCards(data.products, data.intent);
      } else {
        hideProductCards();
      }
    }

  } catch (err) {
    removeTypingIndicator(typingId);
    appendAssistantMessage('❌ Không thể kết nối đến server. Vui lòng thử lại.', 'error');
    console.error('Chat error:', err);
  } finally {
    setLoading(false);
  }
}

// ─── Message rendering ────────────────────────────────────────────────────────
function appendUserMessage(text) {
  const time = getCurrentTime();
  const html = `
    <div class="message-group user-group" style="animation: fadeInUp 0.3s ease">
      <div class="avatar">👤</div>
      <div class="message-content">
        <div class="message-bubble user-bubble">
          <p>${escapeHtml(text)}</p>
        </div>
        <span class="message-time">${time}</span>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
}

function appendAssistantMessage(text, intent = '') {
  const time = getCurrentTime();
  const formattedText = formatMarkdown(text);
  const intentBadge = intent ? `<span style="font-size:11px;color:var(--text-muted);margin-left:8px">${getIntentLabel(intent)}</span>` : '';

  const html = `
    <div class="message-group assistant-group" style="animation: fadeInUp 0.3s ease">
      <div class="avatar">🍔</div>
      <div class="message-content">
        <div class="message-bubble assistant-bubble md-content">
          ${formattedText}
        </div>
        <span class="message-time">${time}${intentBadge}</span>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
}

function showTypingIndicator(loadingNote = '') {
  const id = 'typing-' + Date.now();
  const noteHtml = loadingNote
    ? `<div class="typing-note">${escapeHtml(loadingNote)}</div>`
    : '';
  const html = `
    <div class="message-group assistant-group" id="${id}" style="animation: fadeInUp 0.3s ease">
      <div class="avatar">🍔</div>
      <div class="message-content">
        <div class="typing-bubble">
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
          ${noteHtml}
        </div>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
  return id;
}

function removeTypingIndicator(id) {
  document.getElementById(id)?.remove();
}

// ─── Product Cards ────────────────────────────────────────────────────────────
function showProductCards(products, intent) {
  if (!products || products.length === 0) {
    hideProductCards();
    return;
  }

  productCardsArea.style.display = 'block';

  const titleMap = {
    recommend_product: '🏆 Sản phẩm đề xuất',
    compare_product: '⚖️ So sánh sản phẩm',
    check_stock: '📦 Sản phẩm thay thế',
    create_order: '📝 Sản phẩm',
  };
  productCardsTitle.textContent = titleMap[intent] || '🔍 Sản phẩm tìm thấy';
  productCount.textContent = `${products.length} sản phẩm`;

  productCardsGrid.innerHTML = '';
  products.forEach((p, index) => {
    productCardsGrid.insertAdjacentHTML('beforeend', buildProductCard(p, index + 1));
  });
}

function hideProductCards() {
  productCardsArea.style.display = 'none';
  productCardsGrid.innerHTML = '';
}

function buildProductCard(product, rank) {
  const score = product.score || 0;
  const scorePercent = Math.round(score);

  // Build badges
  const badges = buildBadges(product);

  return `
    <div class="product-card" onclick="showProductDetail('${product.id}')">
      <div class="card-rank">${rank}</div>
      <div class="card-name" title="${escapeHtml(product.name || '')}">${escapeHtml(product.name || 'N/A')}</div>
      <div class="card-sku">${escapeHtml(product.short_code || product.id || '')}</div>
      <div class="card-badges">${badges}</div>
      <div class="card-score-bar">
        <div class="card-score-fill" style="width: ${scorePercent}%"></div>
      </div>
      <div class="card-score-label">Score: ${scorePercent}/100</div>
    </div>
  `;
}

function buildBadges(product) {
  const badges = [];

  // Location badge
  const loc = (product.location || '').toUpperCase();
  if (loc === 'US' || loc === 'USA') badges.push('<span class="badge badge-us">🇺🇸 US</span>');
  else if (loc === 'EU' || loc === 'POLAND' || loc === 'GERMANY') badges.push('<span class="badge badge-eu">🇪🇺 EU</span>');
  else if (loc === 'CHINA') badges.push('<span class="badge badge-china">🇨🇳 China</span>');
  else if (loc && loc !== 'UNKNOWN') badges.push(`<span class="badge badge-default">📍 ${loc}</span>`);

  // Print method badge
  const pm = (product.print_method || '').toUpperCase();
  if (pm.includes('DTG')) badges.push('<span class="badge badge-dtg">🖨️ DTG</span>');
  else if (pm.includes('SUBLIMATION') || pm.includes('SUB')) badges.push('<span class="badge badge-sub">🌈 Sub</span>');
  else if (pm.includes('AOP')) badges.push('<span class="badge badge-aop">🎨 AOP</span>');
  else if (pm && pm !== 'UNKNOWN') badges.push(`<span class="badge badge-default">${pm}</span>`);

  // Lead time badge
  const procMin = product.processing_min || 999;
  if (procMin <= 5) badges.push('<span class="badge badge-fast">⚡ Fast 1-5d</span>');
  else if (procMin <= 10) badges.push('<span class="badge badge-sub">🔵 5-10d</span>');
  else if (procMin < 999) badges.push('<span class="badge badge-slow">🕐 10+d</span>');

  // Inventory badge
  const inv = (product.inventory_status || '').toLowerCase();
  if (inv === 'available') badges.push('<span class="badge badge-inventory-available">✅ In stock</span>');
  else if (inv === 'out_of_stock') badges.push('<span class="badge badge-inventory-oos">⛔ Out of stock</span>');
  else if (inv === 'unknown') badges.push('<span class="badge badge-inventory-unknown">❔ Stock unknown</span>');

  return badges.join('');
}

function applyFilters() {
  let filtered = [...state.allProducts];

  if (state.activeFilters.location) {
    filtered = filtered.filter(p => {
      const loc = (p.location || '').toUpperCase();
      const filter = state.activeFilters.location.toUpperCase();
      if (filter === 'EU') return ['EU', 'POLAND', 'GERMANY', 'NETHERLANDS', 'UK'].includes(loc);
      return loc === filter;
    });
  }

  if (state.activeFilters.print) {
    filtered = filtered.filter(p => {
      const pm = (p.print_method || '').toUpperCase();
      return pm.includes(state.activeFilters.print.toUpperCase());
    });
  }

  if (state.activeFilters.lead !== '999') {
    const maxLead = parseInt(state.activeFilters.lead);
    filtered = filtered.filter(p => (p.processing_min || 999) <= maxLead);
  }

  if (filtered.length > 0) {
    showProductCards(filtered, 'recommend_product');
  } else {
    hideProductCards();
    showToast('Không tìm thấy sản phẩm với bộ lọc này', 'info');
  }
}

function showProductDetail(productId) {
  // Simple detail - could be expanded to modal
  const product = state.allProducts.find(p => p.id === productId);
  if (product) {
    showToast(product.name, 'info');
  }
}

// ─── API Status Check ──────────────────────────────────────────────────────
async function checkAPIStatus() {
  try {
    const resp = await fetch('/api/balance/', { method: 'GET' });
    if (resp.ok) {
      setStatus('online', '✅ API kết nối thành công');
    } else {
      setStatus('warning', '⚠️ API lỗi xác thực');
    }
  } catch {
    setStatus('error', '❌ Không thể kết nối API');
  }
}

function setStatus(state, label) {
  if (statusIndicator) {
    statusIndicator.className = 'status-dot ' + state;
  }
  if (statusLabel) {
    statusLabel.textContent = label;
  }
}

// ─── Utilities ─────────────────────────────────────────────────────────────
function setLoading(isLoading) {
  state.isLoading = isLoading;
  if (sendBtn) sendBtn.disabled = isLoading;
}

function getLoadingText(query) {
  const q = query.toLowerCase();
  if (q.includes('so sánh') || q.includes('compare')) return 'Đang so sánh sản phẩm...';
  if (q.includes('hết hàng') || q.includes('còn hàng') || q.includes('tồn kho')) return 'Đang kiểm tra tồn kho...';
  if (q.includes('đơn hàng') || q.includes('order')) return 'Đang xử lý đơn hàng...';
  return 'Đang truy vấn catalog BurgerPrints...';
}

function getIntentLabel(intent) {
  const map = {
    recommend_product: '🔍 Tìm sản phẩm',
    compare_product: '⚖️ So sánh',
    check_stock: '📦 Kiểm tra kho',
    create_order: '📝 Tạo đơn',
    general_inquiry: '💬 Tư vấn',
  };
  return map[intent] || intent;
}

function formatMarkdown(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    return marked.parse(text);
  }
  
  // Fallback if marked is not loaded
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(.+)$/, '<p>$1</p>');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function scrollToBottom() {
  if (messagesContainer) {
    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior: 'smooth',
    });
  }
}

function getCurrentTime() {
  return new Date().toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function showToast(message, type = 'info') {
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => {
    toast.className = 'toast';
  }, 3000);
}

function clearChat() {
  if (!messagesContainer) return;
  // Keep only welcome message
  const welcome = document.getElementById('welcome-msg');
  messagesContainer.innerHTML = '';
  if (welcome) messagesContainer.appendChild(welcome);
  hideProductCards();
}
