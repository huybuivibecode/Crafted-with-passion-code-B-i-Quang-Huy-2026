/**
 * BurgerPrintsAgent - Frontend Chat Logic (Phiên bản nâng cấp)
 * ChatGPT-like experience: markdown rendering, rich product cards,
 * filter injection, order modal, Vietnamese UI, cache management.
 */

const state = {
  sessionId: document.getElementById('session-id-input')?.value || crypto.randomUUID(),
  isLoading: false,
  ui: {
    showProductSuggestions: true,
    showPartnerColors: true,
  },
  partnerColorCache: {},
  activeFilters: {
    location: '',
    print: '',
    lead: '',
    price: '',
  },
  allProducts: [],
  lastQuery: '',
  orderStep: 1,
};

// DOM refs
const chatPanel = document.getElementById('bp-chat-panel');
const canvasPanel = document.getElementById('bp-canvas-panel');
const landingSection = document.getElementById('bp-landing');
const chatScroll = document.getElementById('bp-chat-scroll');
const messagesContainer = document.getElementById('messages-container');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const charCount = document.getElementById('char-count');
const productCardsArea = document.getElementById('product-cards-area');
const productCardsGrid = document.getElementById('product-cards-grid');
const productCardsTitle = document.getElementById('product-cards-title');
const productCount = document.getElementById('product-count');
const btnToggleProducts = document.getElementById('toggle-products-btn');
const btnTogglePartnerColors = document.getElementById('toggle-partner-colors-btn');
const statusIndicator = document.getElementById('status-indicator');
const statusLabel = document.getElementById('status-label');
const toast = document.getElementById('toast');
const btnNewChat = document.getElementById('btn-new-chat');
const orderModal = document.getElementById('order-modal');
const partnerColorsModal = document.getElementById('partner-colors-modal');
const partnerColorsCloseBtn = document.getElementById('partner-colors-close-btn');
const partnerColorsTitle = document.getElementById('partner-colors-title');
const partnerColorsBody = document.getElementById('partner-colors-body');
const colorPreviewModal = document.getElementById('color-preview-modal');
const colorPreviewCloseBtn = document.getElementById('color-preview-close-btn');
const colorPreviewSwatch = document.getElementById('color-preview-swatch');
const colorPreviewHex = document.getElementById('color-preview-hex');
const btnApplyFilter = document.getElementById('btn-apply-filter');
const btnClearCache = document.getElementById('btn-clear-cache');

const decisionWinnerSubtitle = document.getElementById('bp-winner-subtitle');
const decisionWinnerBase = document.getElementById('bp-winner-base');
const decisionWinnerProd = document.getElementById('bp-winner-prod');
const decisionWinnerQuality = document.getElementById('bp-winner-quality');
const decisionExportBtn = document.getElementById('bp-export-btn');
const decisionTableBody = document.getElementById('bp-factory-table-body');
const decisionInsightsList = document.getElementById('bp-insights-list');
const decisionRankingCards = document.getElementById('bp-ranking-cards');
const splitResizer = document.getElementById('bp-resizer');
const chatInputArea = document.getElementById('bp-input-area');
const canvasContent = document.getElementById('bp-canvas-content');
const canvasFooter = document.getElementById('bp-canvas-footer');
const btnMinimizeChat = document.getElementById('bp-min-chat-btn');
const btnMinimizeCanvas = document.getElementById('bp-min-canvas-btn');

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  configureMarkdown();
  setupEventListeners();
  restoreDraft();
  autoResizeTextarea();
  await Promise.allSettled([checkAPIStatus(), loadConversationHistory()]);
  updateComposerState();
  syncLayoutState();
  applySplitFromStorage();
  chatInput?.focus();
});

function setActiveLayout(isActive) {
  const active = Boolean(isActive);
  if (chatPanel) {
    chatPanel.classList.toggle('lg:basis-full', !active);
    chatPanel.classList.toggle('lg:basis-2/5', active);
  }
  if (canvasPanel) {
    canvasPanel.classList.toggle('hidden', !active);
    canvasPanel.classList.toggle('flex', active);
  }
  if (landingSection) landingSection.classList.toggle('hidden', active);
  if (messagesContainer) messagesContainer.classList.toggle('hidden', !active);
  if (splitResizer) splitResizer.style.display = active ? '' : 'none';

  if (active) {
    applySplitFromStorage();
  } else {
    clearInlineSplit();
    setMinimized('none', { persist: false });
  }
}

function syncLayoutState() {
  const hasMessages = Boolean(messagesContainer?.children?.length);
  setActiveLayout(hasMessages);
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function getSplitStorageKey() {
  return 'bp_split_pct';
}

function getMinimizeStorageKey() {
  return 'bp_minimized';
}

function clearInlineSplit() {
  if (chatPanel) chatPanel.style.flexBasis = '';
  if (canvasPanel) canvasPanel.style.flexBasis = '';
}

function setSplitPercent(pct, { persist = true } = {}) {
  const p = clamp(Number(pct) || 40, 28, 72);
  if (!chatPanel || !canvasPanel) return;
  chatPanel.style.flexBasis = `${p}%`;
  canvasPanel.style.flexBasis = `${100 - p}%`;
  if (persist) localStorage.setItem(getSplitStorageKey(), String(p));
  applyResponsivePanes();
}

function setMinimized(mode, { persist = true } = {}) {
  const m = ['none', 'chat', 'canvas'].includes(mode) ? mode : 'none';
  if (persist) localStorage.setItem(getMinimizeStorageKey(), m);

  if (!chatPanel || !canvasPanel) return;

  if (m === 'chat') {
    chatPanel.style.display = 'none';
    canvasPanel.style.display = 'flex';
    canvasPanel.style.flexBasis = '100%';
    chatPanel.classList.remove('bp-compact-pane');
    canvasPanel.classList.remove('bp-compact-pane');
    productCardsGrid?.classList.remove('bp-compact-grid');
  } else if (m === 'canvas') {
    canvasPanel.style.display = 'none';
    chatPanel.style.display = 'flex';
    chatPanel.style.flexBasis = '100%';
    chatPanel.classList.remove('bp-compact-pane');
    canvasPanel.classList.remove('bp-compact-pane');
    productCardsGrid?.classList.remove('bp-compact-grid');
  } else {
    chatPanel.style.display = '';
    canvasPanel.style.display = '';
    const savedPct = Number(localStorage.getItem(getSplitStorageKey()) || 40);
    setSplitPercent(savedPct, { persist: false });
  }

  if (btnMinimizeChat) {
    btnMinimizeChat.innerHTML = m === 'chat'
      ? '<i class="fa-solid fa-up-right-and-down-left-from-center"></i>'
      : '<i class="fa-solid fa-window-minimize"></i>';
  }
  if (btnMinimizeCanvas) {
    btnMinimizeCanvas.innerHTML = m === 'canvas'
      ? '<i class="fa-solid fa-up-right-and-down-left-from-center"></i>'
      : '<i class="fa-solid fa-window-minimize"></i>';
  }

  if (splitResizer) splitResizer.style.display = m === 'none' ? '' : 'none';
}

function applyResponsivePanes() {
  if (!chatPanel || !canvasPanel) return;
  try {
    const chatW = chatPanel.getBoundingClientRect().width;
    const canvasW = canvasPanel.getBoundingClientRect().width;
    const chatCompact = chatW > 0 && chatW < 520;
    const canvasCompact = canvasW > 0 && canvasW < 980;
    chatPanel.classList.toggle('bp-compact-pane', chatCompact);
    canvasPanel.classList.toggle('bp-compact-pane', canvasCompact);
    productCardsGrid?.classList.toggle('bp-compact-grid', chatCompact);
  } catch {
  }
}

function applySplitFromStorage() {
  if (!chatPanel || !canvasPanel) return;
  const savedMin = localStorage.getItem(getMinimizeStorageKey()) || 'none';
  const savedPct = Number(localStorage.getItem(getSplitStorageKey()) || 40);
  setMinimized(savedMin, { persist: false });
  if (savedMin === 'none') setSplitPercent(savedPct, { persist: false });
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

function setupEventListeners() {
  // Send
  sendBtn?.addEventListener('click', () => handleSend());
  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });
  chatInput?.addEventListener('input', () => {
    updateComposerState();
    persistDraft();
    autoResizeTextarea();
  });

  // Quick prompts & composer chips
  [...document.querySelectorAll('.quick-btn'), ...document.querySelectorAll('.composer-chip')].forEach((btn) => {
    btn.addEventListener('click', () => {
      const prompt = btn.dataset.prompt || '';
      submitPrompt(prompt);
    });
  });

  // Filter tags
  document.querySelectorAll('.filter-tag').forEach((tag) => {
    tag.addEventListener('click', () => {
      const filterType = tag.dataset.filter;
      const filterValue = tag.dataset.value;
      document.querySelectorAll(`.filter-tag[data-filter="${filterType}"]`).forEach((item) => {
        item.classList.remove('active');
      });
      tag.classList.add('active');
      state.activeFilters[filterType] = filterValue;
    });
  });

  // Apply filter button - inject vào query
  btnApplyFilter?.addEventListener('click', () => {
    const filterQuery = buildFilterQuery();
    if (filterQuery) {
      submitPrompt(filterQuery);
    } else {
      showToast('Hãy chọn ít nhất một bộ lọc', 'info');
    }
  });

  // New chat
  btnNewChat?.addEventListener('click', () => {
    state.sessionId = crypto.randomUUID();
    state.allProducts = [];
    state.lastQuery = '';
    clearDraft();
    clearChat();
    updateComposerState();
    chatInput?.focus();
    showToast('Đã tạo session mới', 'info');
  });

  btnMinimizeChat?.addEventListener('click', () => {
    const current = localStorage.getItem(getMinimizeStorageKey()) || 'none';
    setMinimized(current !== 'none' ? 'none' : 'chat');
  });

  btnMinimizeCanvas?.addEventListener('click', () => {
    const current = localStorage.getItem(getMinimizeStorageKey()) || 'none';
    setMinimized(current !== 'none' ? 'none' : 'canvas');
  });

  if (splitResizer) {
    splitResizer.addEventListener('pointerdown', (e) => {
      const minimized = localStorage.getItem(getMinimizeStorageKey()) || 'none';
      if (minimized !== 'none') return;
      if (!chatPanel || !canvasPanel) return;
      const shell = splitResizer.parentElement;
      if (!shell) return;

      const startX = e.clientX;
      const rect = shell.getBoundingClientRect();
      const startPct = Number(localStorage.getItem(getSplitStorageKey()) || 40);

      splitResizer.setPointerCapture(e.pointerId);
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';

      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const pctDelta = (dx / rect.width) * 100;
        setSplitPercent(startPct + pctDelta);
      };

      const onUp = () => {
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        window.removeEventListener('pointermove', onMove);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp, { once: true });
    });
  }

  // Cache clear
  btnClearCache?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/cache/stats/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
      });
      if (res.ok) {
        showToast('Cache đã được xoá. Catalog sẽ tải lại từ API.', 'success');
      } else {
        showToast('Không xoá được cache', 'error');
      }
    } catch {
      showToast('Không kết nối được server', 'error');
    }
  });

  btnToggleProducts?.addEventListener('click', () => {
    state.ui.showProductSuggestions = !state.ui.showProductSuggestions;
    applyProductSuggestionsVisibility();
  });

  btnTogglePartnerColors?.addEventListener('click', () => {
    state.ui.showPartnerColors = !state.ui.showPartnerColors;
    applyPartnerColorsVisibility();
    if (state.ui.showPartnerColors) {
      const first = Array.isArray(state.allProducts) ? state.allProducts[0] : null;
      const productId = first?.id || first?.short_code || '';
      if (productId) {
        openPartnerColorsModal(productId, first?.name || '');
      } else {
        showToast('Chọn 1 sản phẩm để xem màu theo partner', 'info');
      }
    } else {
      closePartnerColorsModal();
    }
  });

  productCardsArea?.addEventListener('click', async (event) => {
    const actionEl = event.target.closest('[data-card-action]');
    if (actionEl) {
      event.preventDefault();
      event.stopPropagation();
      const action = actionEl.dataset.cardAction;
      const productId = actionEl.dataset.productId || '';

      if (action === 'toggle-partner-colors') {
        const product = state.allProducts.find((p) => (p.id || p.short_code) === productId) || {};
        openPartnerColorsModal(productId, product?.name || '');
      }
      if (action === 'preview-color') {
        openColorPreview(actionEl.dataset.colorHex || '');
      }
      return;
    }

    const card = event.target.closest('.product-card');
    if (!card) return;
    const productId = card.dataset.productId || '';
    if (productId) showProductDetail(productId);
  });

  // Message action delegation (copy, prompt, retry)
  messagesContainer?.addEventListener('click', async (event) => {
    const actionEl = event.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;

    if (action === 'copy') {
      const text = decodeURIComponent(actionEl.dataset.copy || '');
      try {
        await navigator.clipboard.writeText(text);
        showToast('Đã sao chép câu trả lời', 'success');
      } catch {
        showToast('Không sao chép được', 'error');
      }
    }

    if (action === 'prompt') {
      const prompt = decodeURIComponent(actionEl.dataset.prompt || '');
      submitPrompt(prompt);
    }

    if (action === 'retry') {
      const prompt = decodeURIComponent(actionEl.dataset.prompt || state.lastQuery);
      submitPrompt(prompt);
    }

    if (action === 'order') {
      openOrderModal();
    }
  });

  // Order modal
  document.getElementById('modal-close-btn')?.addEventListener('click', closeOrderModal);
  document.getElementById('order-btn-next')?.addEventListener('click', handleOrderNext);
  document.getElementById('order-btn-prev')?.addEventListener('click', handleOrderPrev);
  orderModal?.addEventListener('click', (e) => {
    if (e.target === orderModal) closeOrderModal();
  });

  partnerColorsCloseBtn?.addEventListener('click', closePartnerColorsModal);
  partnerColorsModal?.addEventListener('click', (e) => {
    const actionEl = e.target.closest('[data-card-action="preview-color"]');
    if (actionEl) {
      e.preventDefault();
      e.stopPropagation();
      openColorPreview(actionEl.dataset.colorHex || '');
      return;
    }
    if (e.target === partnerColorsModal) closePartnerColorsModal();
  });

  colorPreviewCloseBtn?.addEventListener('click', closeColorPreview);
  colorPreviewModal?.addEventListener('click', (e) => {
    if (e.target === colorPreviewModal) closeColorPreview();
  });
}

// ---------------------------------------------------------------------------
// Filter → Query injection
// ---------------------------------------------------------------------------

function buildFilterQuery() {
  const parts = [];

  const locMap = { US: 'thị trường Mỹ (US)', EU: 'thị trường EU', China: 'sản xuất tại China', Vietnam: 'sản xuất tại Vietnam' };
  if (state.activeFilters.location) {
    parts.push(locMap[state.activeFilters.location] || state.activeFilters.location);
  }

  if (state.activeFilters.print) {
    parts.push(`công nghệ in ${state.activeFilters.print}`);
  }

  if (state.activeFilters.lead) {
    const leadMap = { '5': 'giao hàng nhanh trong 1-5 ngày', '10': 'lead time tối đa 10 ngày' };
    parts.push(leadMap[state.activeFilters.lead] || `lead time ≤ ${state.activeFilters.lead} ngày`);
  }

  const priceMap = { under10: 'giá dưới $10', under15: 'giá dưới $15', over15: 'giá trên $15' };
  if (state.activeFilters.price) {
    parts.push(priceMap[state.activeFilters.price] || state.activeFilters.price);
  }

  if (!parts.length) return '';

  return `Tìm sản phẩm POD phù hợp: ${parts.join(', ')}`;
}

// ---------------------------------------------------------------------------
// Markdown config
// ---------------------------------------------------------------------------

function configureMarkdown() {
  if (typeof marked === 'undefined') return;
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
}

// ---------------------------------------------------------------------------
// Draft persistence
// ---------------------------------------------------------------------------

function getDraftKey() {
  return `bp-chat-draft:${state.sessionId}`;
}

function restoreDraft() {
  if (!chatInput) return;
  const draft = localStorage.getItem(getDraftKey()) || '';
  if (draft) {
    chatInput.value = draft;
  }
}

function persistDraft() {
  if (!chatInput) return;
  localStorage.setItem(getDraftKey(), chatInput.value || '');
}

function clearDraft() {
  localStorage.removeItem(getDraftKey());
  if (chatInput) chatInput.value = '';
}

// ---------------------------------------------------------------------------
// Composer state
// ---------------------------------------------------------------------------

function updateComposerState() {
  const len = chatInput?.value?.length || 0;
  if (charCount) {
    charCount.textContent = `${len}/500`;
    charCount.style.color = len > 450 ? '#EF4444' : 'var(--text-muted)';
  }
  if (sendBtn) {
    sendBtn.disabled = state.isLoading || len === 0;
  }
}

function autoResizeTextarea() {
  if (!chatInput) return;
  chatInput.style.height = 'auto';
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 180)}px`;
}

// ---------------------------------------------------------------------------
// History load
// ---------------------------------------------------------------------------

async function loadConversationHistory() {
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(state.sessionId)}/`, { method: 'GET' });
    if (!response.ok) return;

    const data = await response.json();
    const messages = Array.isArray(data.messages) ? data.messages : [];
    if (!messages.length) return;

    messagesContainer.innerHTML = '';
    let lastAssistantPayload = null;
    messages.forEach((message) => {
      if (message.role === 'user') {
        appendUserMessage(message.content, {
          skipAnimation: true,
          timeLabel: formatHistoryTime(message.created_at),
        });
        return;
      }

      const products = getProductsFromMessageMetadata(message.metadata);
      const payload = {
        response: message.content,
        intent: message.intent || '',
        products,
        reasons: message.metadata?.reasons || [],
        winner: message.metadata?.winner || {},
        alternatives: message.metadata?.alternatives || [],
        follow_ups: buildFollowUpsFromPayload({
          intent: message.intent || '',
          products,
          winner: message.metadata?.winner || {},
          alternatives: message.metadata?.alternatives || [],
        }),
      };

      appendAssistantMessage(payload.response, {
        intent: payload.intent,
        products: payload.products,
        reasons: payload.reasons,
        winner: payload.winner,
        alternatives: payload.alternatives,
        followUps: payload.follow_ups,
        skipAnimation: true,
        timeLabel: formatHistoryTime(message.created_at),
        fromHistory: true,
      });
      lastAssistantPayload = payload;
    });

    setActiveLayout(true);
    renderDecisionCanvas({ products: lastAssistantPayload?.products || [] });
    scrollToBottom(false);
  } catch (err) {
    console.error('History load error:', err);
  }
}

// ---------------------------------------------------------------------------
// Send handler
// ---------------------------------------------------------------------------

async function handleSend(forcedQuery = '') {
  const query = (forcedQuery || chatInput?.value || '').trim();
  if (!query || state.isLoading) return;

  state.lastQuery = query;
  setActiveLayout(true);
  appendUserMessage(query);
  clearDraft();
  updateComposerAfterSend();

  const typingId = showTypingIndicator(getLoadingText(query));
  setLoading(true);

  try {
    const response = await fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({
        query,
        session_id: state.sessionId,
      }),
    });

    const data = await response.json();
    removeTypingIndicator(typingId);

    if (!response.ok && data.error) {
      appendAssistantMessage(`❌ Không thể xử lý lúc này.\n\n- Lỗi: ${data.error}`, {
        intent: 'general_inquiry',
        followUps: [query],
        error: true,
      });
      return;
    }

    state.allProducts = Array.isArray(data.products) ? data.products : [];

    // Update product cards nếu có sản phẩm
    if (state.allProducts.length) {
      showProductCards(state.allProducts, data.intent);
    } else {
      hideProductCards();
    }

    renderDecisionCanvas(data);
    appendAssistantMessage(data.response || 'Xin lỗi, tôi chưa tạo được câu trả lời phù hợp.', {
      intent: data.intent || '',
      products: data.products || [],
      reasons: data.reasons || [],
      winner: data.winner || {},
      alternatives: data.alternatives || [],
      followUps: data.follow_ups || buildFollowUpsFromPayload(data),
      error: Boolean(data.error && !data.response),
      nodeTrace: data.node_trace || [],
    });
  } catch (err) {
    removeTypingIndicator(typingId);
    console.error('Chat error:', err);
    appendAssistantMessage('❌ Không thể kết nối tới server.\n\nBạn thử gửi lại sau ít giây nhé.', {
      intent: 'general_inquiry',
      followUps: [query],
      error: true,
    });
  } finally {
    setLoading(false);
    updateComposerState();
    chatInput?.focus();
  }
}

function submitPrompt(prompt) {
  if (!prompt || state.isLoading || !chatInput) return;
  chatInput.value = prompt;
  updateComposerState();
  autoResizeTextarea();
  handleSend(prompt);
}

function updateComposerAfterSend() {
  if (!chatInput) return;
  chatInput.value = '';
  autoResizeTextarea();
  updateComposerState();
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function appendUserMessage(text, options = {}) {
  const time = options.timeLabel || getCurrentTime();
  const animation = options.skipAnimation ? '' : 'style="animation: fadeInUp 0.3s ease"';
  const html = `
    <div class="flex justify-end" ${animation}>
      <div class="max-w-[92%] sm:max-w-[80%]">
        <div class="rounded-2xl rounded-tr-sm bg-brandBlue text-white px-4 py-3 shadow-sm">
          <div class="text-sm leading-relaxed">${escapeHtml(text)}</div>
        </div>
        <div class="mt-1 text-[11px] text-ink/50 text-right">${time}</div>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
}

function appendAssistantMessage(text, options = {}) {
  const time = options.timeLabel || getCurrentTime();
  const formattedText = formatMarkdown(text);
  const intentBadge = options.intent ? `
    <span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">
      ${escapeHtml(getIntentLabel(options.intent))}
    </span>
  ` : '';
  const copyPayload = encodeURIComponent(text || '');
  const animation = options.skipAnimation ? '' : 'style="animation: fadeInUp 0.3s ease"';
  const historyPill = options.fromHistory ? `
    <span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white text-ink/60 text-xs font-semibold border border-black/10">
      <i class="fa-solid fa-clock-rotate-left text-ink/40"></i> Lịch sử
    </span>
  ` : '';

  const html = `
    <div class="flex justify-start" ${animation}>
      <div class="max-w-[96%] sm:max-w-[86%]">
        <div class="flex items-start gap-3">
          <div class="h-9 w-9 rounded-xl bg-white border border-black/10 shadow-sm flex items-center justify-center shrink-0">
            <i class="fa-solid fa-robot text-ink/70"></i>
          </div>
          <div class="rounded-2xl rounded-tl-sm bg-white border border-black/5 px-4 py-3 shadow-sm w-full">
            <div class="flex items-center justify-between gap-3 flex-wrap">
              <div class="flex items-center gap-2 flex-wrap">
                ${intentBadge}
                ${historyPill}
              </div>
              <div class="flex items-center gap-2">
                <button class="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition" data-action="copy" data-copy="${copyPayload}" title="Sao chép">
                  <i class="fa-solid fa-copy text-ink/60"></i> Copy
                </button>
                ${options.intent === 'recommend_product' || options.intent === 'compare_product' ?
                  `<button class="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition" data-action="order" title="Tạo đơn hàng">
                    <i class="fa-solid fa-box text-ink/60"></i> Tạo đơn
                  </button>` : ''}
              </div>
            </div>

            <div class="mt-3 text-sm leading-relaxed text-ink/80 md-content">
              ${formattedText}
            </div>

            ${buildAssistantExtras(options)}

            <div class="mt-2 text-[11px] text-ink/50">${time}</div>
          </div>
        </div>
      </div>
    </div>
  `;
  messagesContainer.insertAdjacentHTML('beforeend', html);
  scrollToBottom();
}

function buildAssistantExtras(options = {}) {
  const products = Array.isArray(options.products) ? options.products.slice(0, 3) : [];
  const reasons = Array.isArray(options.reasons) ? options.reasons.slice(0, 3) : [];
  const followUps = Array.isArray(options.followUps) ? options.followUps.slice(0, 4) : [];
  const winner = options.winner || {};

  // Winner card - nâng cấp với thêm thông tin
  const winnerHtml = winner?.name
    ? `
      <div class="mt-4 rounded-2xl bg-white border border-black/10 shadow-sm p-4">
        <div class="text-xs font-bold text-ink/60">🏆 Kết quả tốt nhất</div>
        <div class="mt-1 text-sm font-extrabold">${escapeHtml(winner.name)}</div>
        <div class="mt-0.5 text-xs text-ink/60 font-mono">${escapeHtml(winner.short_code || '')}</div>
        <div class="mt-2 flex flex-wrap gap-2">${buildBadges(winner)}</div>
        ${winner.suggested_selling_price ? `<div class="mt-2 text-xs text-ink/60">💰 Giá bán đề xuất: <span class="font-semibold">$${Number(winner.suggested_selling_price).toFixed(2)}</span> | Lợi nhuận: <span class="font-semibold">$${Number(winner.profit || 0).toFixed(2)}</span></div>` : ''}
      </div>
    `
    : '';

  // Reasons
  const reasonHtml = reasons.length
    ? `
      <div class="mt-4 rounded-2xl bg-appBg/60 border border-black/5 p-4">
        <div class="text-xs font-bold text-ink/60">✅ Lý do gợi ý</div>
        <div class="mt-2 space-y-2 text-sm text-ink/75">
          ${reasons.map((reason) => `<div class="rounded-xl bg-white border border-black/10 p-3">${formatMarkdown(reason)}</div>`).join('')}
        </div>
      </div>
    `
    : '';

  // Inline product strip
  const productsHtml = products.length
    ? `
      <div class="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        ${products.map((product, index) => buildInlineProductCard(product, index + 1)).join('')}
      </div>
    `
    : '';

  // Follow-up chips
  const followUpHtml = followUps.length
    ? `
      <div class="mt-4 flex flex-wrap gap-2">
        ${followUps.map((prompt) => `
          <button class="px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition" data-action="prompt" data-prompt="${encodeURIComponent(prompt)}">
            ${escapeHtml(prompt)}
          </button>
        `).join('')}
      </div>
    `
    : '';

  // Error: retry chip
  const retryHtml = options.error ? `
    <div class="mt-4">
      <button class="px-3 py-2 rounded-xl bg-brandOrange/10 text-brandOrange border border-brandOrange/20 text-xs font-semibold hover:bg-brandOrange/15 transition" data-action="retry" data-prompt="${encodeURIComponent(state.lastQuery || '')}">
        <i class="fa-solid fa-rotate-right mr-2"></i> Gửi lại
      </button>
    </div>
  ` : '';

  if (!winnerHtml && !reasonHtml && !productsHtml && !followUpHtml && !retryHtml) return '';

  return `
    <div class="assistant-extras">
      ${winnerHtml}
      ${reasonHtml}
      ${productsHtml}
      ${followUpHtml}
      ${retryHtml}
    </div>
  `;
}

function buildInlineProductCard(product, rank) {
  const prompt = `Phân tích chi tiết ${product.name || product.short_code || 'sản phẩm này'}`;
  const thumbnail = product.thumbnail
    ? `<img class="h-12 w-12 rounded-xl object-cover border border-black/10" src="${escapeHtml(product.thumbnail)}" alt="${escapeHtml(product.name || '')}" onerror="this.style.display='none'">`
    : `<div class="h-12 w-12 rounded-xl bg-appBg border border-black/10 flex items-center justify-center text-ink/50"><i class="fa-solid fa-shirt"></i></div>`;
  const priceInfo = product.price_min && product.price_max
    ? `<div class="text-[11px] text-ink/60 mt-1">Base: <span class="font-semibold text-ink">${product.price_min === product.price_max ? `$${product.price_min.toFixed(2)}` : `$${product.price_min.toFixed(2)}–$${product.price_max.toFixed(2)}`}</span></div>`
    : '';
  return `
    <div class="rounded-xl border border-black/10 bg-white p-3 hover:shadow-sm transition">
      <div class="flex items-start justify-between gap-2">
        <div class="flex items-start gap-3 min-w-0">
          ${thumbnail}
          <div class="min-w-0">
            <div class="text-xs font-bold tracking-tight truncate">${escapeHtml(product.name || 'N/A')}</div>
            <div class="text-[11px] text-ink/60 font-mono mt-0.5">${escapeHtml(product.short_code || product.id || '')}</div>
            ${priceInfo}
            <div class="mt-2 flex flex-wrap gap-2">${buildBadges(product)}</div>
            ${buildPartnersInfo(product)}
          </div>
        </div>
        <span class="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-full bg-appBg text-ink/70 text-[11px] font-semibold border border-black/10">
          <i class="fa-solid fa-gauge-high text-brandBlue"></i> ${Math.round(product.score || 0)}/100
        </span>
      </div>
      <button class="mt-3 w-full h-10 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition" data-action="prompt" data-prompt="${encodeURIComponent(prompt)}">
        Xem chi tiết →
      </button>
    </div>
  `;
}

function buildPartnersInfo(product) {
  const partners = product.partners || [];
  if (!partners.length) return '';
  const displayed = partners.slice(0, 2).map(p => escapeHtml(p)).join(', ');
  const more = partners.length > 2 ? ` (+${partners.length - 2})` : '';
  return `<div class="text-[11px] text-ink/60 mt-1"><i class="fa-solid fa-industry text-brandOrange mr-1"></i> ${displayed}${more}</div>`;
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function showTypingIndicator(loadingNote = '') {
  const id = `typing-${Date.now()}`;
  const noteHtml = loadingNote ? `<div class="mt-2 text-xs text-ink/50">${escapeHtml(loadingNote)}</div>` : '';
  const html = `
    <div class="flex justify-start" id="${id}" style="animation: fadeInUp 0.3s ease">
      <div class="max-w-[96%] sm:max-w-[86%]">
        <div class="flex items-start gap-3">
          <div class="h-9 w-9 rounded-xl bg-white border border-black/10 shadow-sm flex items-center justify-center shrink-0">
            <i class="fa-solid fa-robot text-ink/70"></i>
          </div>
          <div class="rounded-2xl rounded-tl-sm bg-white border border-black/5 px-4 py-3 shadow-sm">
            <div class="text-sm text-ink/60 flex items-center gap-2">
              <span class="h-2 w-2 rounded-full bg-brandOrange animate-pulse"></span>
              Thinking…
            </div>
            ${noteHtml}
          </div>
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

// ---------------------------------------------------------------------------
// Product cards
// ---------------------------------------------------------------------------

function showProductCards(products, intent) {
  if (!products || products.length === 0) {
    hideProductCards();
    return;
  }

  productCardsArea?.classList.remove('hidden');
  const titleMap = {
    recommend_product: '🏆 Sản phẩm gợi ý',
    compare_product: '⚖️ Sản phẩm so sánh',
    check_stock: '📦 Sản phẩm còn hàng',
    create_order: '📋 Sản phẩm',
  };
  if (productCardsTitle) productCardsTitle.textContent = titleMap[intent] || '📦 Sản phẩm tìm thấy';
  if (productCount) productCount.textContent = `${products.length} sản phẩm`;
  if (productCardsGrid) {
    productCardsGrid.innerHTML = '';
    products.forEach((product, index) => {
      productCardsGrid.insertAdjacentHTML('beforeend', buildProductCard(product, index + 1));
    });
  }

  applyProductSuggestionsVisibility();
  applyPartnerColorsVisibility();
}

function hideProductCards() {
  productCardsArea?.classList.add('hidden');
  if (productCardsGrid) productCardsGrid.innerHTML = '';
}

function applyProductSuggestionsVisibility() {
  const show = Boolean(state.ui.showProductSuggestions);
  if (productCardsGrid) productCardsGrid.style.display = show ? 'grid' : 'none';
  if (btnToggleProducts) {
    btnToggleProducts.textContent = show ? 'Ẩn gợi ý' : 'Hiện gợi ý';
    btnToggleProducts.classList.toggle('active', !show);
  }
}

function applyPartnerColorsVisibility() {
  const show = Boolean(state.ui.showPartnerColors);
  if (productCardsArea) productCardsArea.classList.toggle('partner-colors-hidden', !show);
  if (btnTogglePartnerColors) {
    btnTogglePartnerColors.textContent = show ? 'Ẩn màu theo partner' : 'Hiện màu theo partner';
    btnTogglePartnerColors.classList.toggle('active', !show);
  }
}

async function openPartnerColorsModal(productId, productName = '') {
  if (!productId || !state.ui.showPartnerColors) return;
  if (!partnerColorsModal || !partnerColorsBody) return;

  if (partnerColorsTitle) {
    const label = productName ? `${productName} (${productId})` : productId;
    partnerColorsTitle.textContent = `🎨 Màu theo partner — ${label}`;
  }

  partnerColorsBody.innerHTML = '<div class="mini-partners-text">Đang tải màu theo partner…</div>';
  partnerColorsModal.style.display = 'flex';

  try {
    const partnerColorMap = await getPartnerColorMap(productId);
    renderPartnerColorsModal(partnerColorMap);
  } catch {
    partnerColorsBody.innerHTML = '<div class="mini-partners-text">Không tải được màu theo partner.</div>';
  }
}

function closePartnerColorsModal() {
  if (partnerColorsModal) partnerColorsModal.style.display = 'none';
}

async function getPartnerColorMap(productId) {
  if (state.partnerColorCache[productId]) return state.partnerColorCache[productId];
  const res = await fetch(`/api/products/${encodeURIComponent(productId)}/`, { method: 'GET' });
  if (!res.ok) throw new Error('fetch_failed');
  const detail = await res.json();
  const map = buildPartnerColorMap(detail);
  state.partnerColorCache[productId] = map;
  return map;
}

function buildPartnerColorMap(detail) {
  const variations = Array.isArray(detail?.variations) ? detail.variations : [];
  const availableColors = Array.isArray(detail?.available_colors) ? detail.available_colors : [];
  const colorHexByName = new Map();

  availableColors.forEach((c) => {
    if (!c) return;
    if (typeof c === 'string') {
      colorHexByName.set(String(c).trim().toLowerCase(), '');
      return;
    }
    if (typeof c === 'object') {
      const name = String(c.name || '').trim();
      const hex = String(c.color_hex || '').trim();
      if (name) colorHexByName.set(name.toLowerCase(), hex);
    }
  });

  const byPartner = new Map();
  variations.forEach((v) => {
    if (!v || typeof v !== 'object') return;
    const partner = String(v.partner_name || v.partner || '').trim();
    const colorName = String(v.color || '').trim();
    let hex = String(v.color_hex || '').trim();
    if (!hex && colorName) hex = String(colorHexByName.get(colorName.toLowerCase()) || '').trim();
    if (!partner || !hex) return;

    if (!byPartner.has(partner)) byPartner.set(partner, new Map());
    const key = hex.toLowerCase();
    if (!byPartner.get(partner).has(key)) {
      byPartner.get(partner).set(key, { name: colorName, hex });
    }
  });

  const entries = Array.from(byPartner.entries())
    .map(([partner, colorsMap]) => [partner, Array.from(colorsMap.values())])
    .sort((a, b) => (b[1].length - a[1].length) || String(a[0]).localeCompare(String(b[0])));

  return Object.fromEntries(entries);
}

function renderPartnerColorsModal(partnerColorMap) {
  if (!partnerColorsBody) return;
  const partners = Object.keys(partnerColorMap || {});
  if (!partners.length) {
    partnerColorsBody.innerHTML = '<div class="mini-partners-text">Chưa có dữ liệu màu theo partner cho sản phẩm này.</div>';
    return;
  }

  const html = partners.map((partner) => {
    const colors = Array.isArray(partnerColorMap[partner]) ? partnerColorMap[partner] : [];
    const swatches = colors.slice(0, 60).map((c) => {
      const hex = String(c?.hex || '').trim();
      if (!hex) return '';
      return `<button class="color-swatch" type="button" style="background:${escapeHtml(hex)}" title="${escapeHtml(hex)}" data-hex="${escapeHtml(hex)}" data-card-action="preview-color" data-color-hex="${escapeHtml(hex)}"></button>`;
    }).join('');

    return `
      <div class="partner-row">
        <div class="partner-row-header">
          <div class="partner-row-title">${escapeHtml(partner)}</div>
          <div class="partner-row-count">${colors.length} màu</div>
        </div>
        <div class="swatch-row">${swatches}</div>
      </div>
    `;
  }).join('');

  partnerColorsBody.innerHTML = html;
}

function openColorPreview(hex) {
  const cleaned = String(hex || '').trim();
  if (!cleaned || !/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(cleaned)) return;
  if (!colorPreviewModal || !colorPreviewSwatch || !colorPreviewHex) return;
  colorPreviewSwatch.style.background = cleaned;
  colorPreviewHex.textContent = cleaned.toUpperCase();
  colorPreviewModal.style.display = 'flex';
}

function closeColorPreview() {
  if (colorPreviewModal) colorPreviewModal.style.display = 'none';
}

function buildProductCard(product, rank) {
  const scorePercent = Math.round(product.score || 0);
  const thumbnail = product.thumbnail
    ? `<img class="h-12 w-12 rounded-xl object-cover border border-black/10" src="${escapeHtml(product.thumbnail)}" alt="${escapeHtml(product.name || '')}" onerror="this.style.display='none'">`
    : `<div class="h-12 w-12 rounded-xl bg-appBg border border-black/10 flex items-center justify-center text-ink/50"><i class="fa-solid fa-shirt"></i></div>`;
  const priceInfo = product.price_min
    ? `<div class="text-xs text-ink/60 mt-1">Base: <span class="font-semibold text-ink">${product.price_min === product.price_max ? `$${Number(product.price_min).toFixed(2)}` : `$${Number(product.price_min).toFixed(2)}–$${Number(product.price_max).toFixed(2)}`}</span></div>`
    : '';
  const profitInfo = product.profit
    ? `<div class="text-xs text-ink/60 mt-1">Profit/order: <span class="font-semibold text-emerald-600">$${Number(product.profit).toFixed(2)}</span></div>`
    : '';

  const productId = product.id || product.short_code || '';
  const partners = Array.isArray(product.partners) ? product.partners.filter(Boolean) : [];
  const partnerText = partners.length ? partners.slice(0, 3).map(p => escapeHtml(p)).join(', ') : '';
  const morePartners = partners.length > 3 ? ` (+${partners.length - 3})` : '';
  const partnersHtml = partners.length ? `<div class="text-xs text-ink/60 mt-1"><i class="fa-solid fa-industry text-brandOrange mr-1"></i> ${partnerText}${morePartners}</div>` : '';

  return `
    <div class="rounded-2xl border border-black/10 bg-white p-4 hover:shadow-sm transition cursor-pointer" data-product-id="${escapeHtml(productId)}">
      <div class="flex items-start justify-between gap-3">
        <div class="flex items-start gap-3 min-w-0">
          ${thumbnail}
          <div class="min-w-0">
            <div class="text-xs font-bold text-ink/60">#${rank}</div>
            <div class="text-sm font-extrabold leading-tight truncate" title="${escapeHtml(product.name || '')}">${escapeHtml(product.name || 'N/A')}</div>
            <div class="text-xs text-ink/60 font-mono mt-0.5">${escapeHtml(product.short_code || product.id || '')}</div>
            ${priceInfo}
            ${profitInfo}
            ${partnersHtml}
          </div>
        </div>
        <div class="shrink-0 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">
          <i class="fa-solid fa-gauge-high text-brandBlue"></i> ${scorePercent}/100
        </div>
      </div>

      <div class="mt-3 flex flex-wrap gap-2">
        ${buildBadges(product)}
      </div>

      <div class="mt-4 flex items-center gap-2">
        <button class="px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition" type="button" data-card-action="toggle-partner-colors" data-product-id="${escapeHtml(productId)}">
          <i class="fa-solid fa-palette text-brandOrange mr-2"></i> Màu theo partner
        </button>
      </div>

      <div class="mt-3 h-2 rounded-full bg-appBg border border-black/5 overflow-hidden">
        <div class="h-full bg-brandBlue" style="width:${scorePercent}%"></div>
      </div>
    </div>
  `;
}

function buildBadges(product) {
  const badges = [];
  const loc = (product.location || '').toUpperCase();
  if (loc === 'US' || loc === 'USA') badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brandBlue/10 text-brandBlue text-xs font-semibold border border-brandBlue/20">🇺🇸 US</span>');
  else if (['EU', 'POLAND', 'GERMANY', 'NETHERLANDS', 'UK'].includes(loc)) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 text-violet-700 text-xs font-semibold border border-violet-500/20">🇪🇺 EU</span>');
  else if (loc === 'CHINA') badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/10 text-red-700 text-xs font-semibold border border-red-500/20">🇨🇳 China</span>');
  else if (loc === 'VIETNAM') badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-700 text-xs font-semibold border border-emerald-500/20">🇻🇳 VN</span>');
  else if (loc && loc !== 'UNKNOWN') badges.push(`<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">${escapeHtml(loc)}</span>`);

  const pm = (product.print_method || '').toUpperCase();
  if (pm.includes('DTG')) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-700 text-xs font-semibold border border-emerald-500/20">DTG</span>');
  else if (pm.includes('DTF')) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-700 text-xs font-semibold border border-emerald-500/20">DTF</span>');
  else if (pm.includes('SUBLIMATION') || pm.includes('SUB')) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 text-amber-700 text-xs font-semibold border border-amber-500/20">Sub</span>');
  else if (pm.includes('AOP')) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-pink-500/10 text-pink-700 text-xs font-semibold border border-pink-500/20">AOP</span>');
  else if (pm.includes('EMBROIDERY')) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">Thêu</span>');
  else if (pm && pm !== 'UNKNOWN') badges.push(`<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">${escapeHtml(pm)}</span>`);

  const procMin = product.processing_min || 999;
  if (procMin <= 5) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brandOrange/10 text-brandOrange text-xs font-semibold border border-brandOrange/20">⚡ 1-5d</span>');
  else if (procMin <= 10) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brandBlue/10 text-brandBlue text-xs font-semibold border border-brandBlue/20">≤10d</span>');
  else if (procMin < 999) badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">10+d</span>');

  const inv = (product.inventory_status || '').toLowerCase();
  if (inv === 'available') badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-700 text-xs font-semibold border border-emerald-500/20">✅ In stock</span>');
  else if (inv === 'out_of_stock') badges.push('<span class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/10 text-red-700 text-xs font-semibold border border-red-500/20">❌ Out</span>');

  return badges.join('');
}

// ---------------------------------------------------------------------------
// Filter client-side (after filter applied via query injection is different)
// Keep this for client-side card filtering only
// ---------------------------------------------------------------------------

function hasActiveFilter() {
  return Boolean(state.activeFilters.location || state.activeFilters.print || state.activeFilters.lead);
}

function showProductDetail(productId) {
  const product = state.allProducts.find((item) => item.id === productId || item.short_code === productId);
  if (!product) return;
  const prompt = `Phân tích chi tiết ${product.name || product.short_code}`;
  if (chatInput) {
    chatInput.value = prompt;
    persistDraft();
    updateComposerState();
    autoResizeTextarea();
    chatInput.focus();
  }
  showToast('Đã điền prompt phân tích sản phẩm', 'info');
}

// ---------------------------------------------------------------------------
// Order Modal
// ---------------------------------------------------------------------------

function openOrderModal() {
  state.orderStep = 1;
  if (orderModal) {
    orderModal.style.display = 'flex';
    document.getElementById('order-step-1').style.display = 'block';
    document.getElementById('order-step-2').style.display = 'block';
    document.getElementById('order-step-3').style.display = 'none';
    document.getElementById('order-btn-prev').style.display = 'none';
    document.getElementById('order-btn-next').textContent = 'Tiếp theo →';
  }
}

function closeOrderModal() {
  if (orderModal) orderModal.style.display = 'none';
}

function handleOrderNext() {
  if (state.orderStep === 1) {
    // Validate step 1 fields
    const sku = document.getElementById('order-sku')?.value?.trim();
    const size = document.getElementById('order-size')?.value?.trim();
    const qty = document.getElementById('order-qty')?.value;
    if (!sku || !size || !qty) {
      showToast('Vui lòng điền đầy đủ thông tin sản phẩm', 'error');
      return;
    }
    state.orderStep = 2;
    document.getElementById('order-btn-prev').style.display = 'inline-flex';
    document.getElementById('order-btn-next').textContent = 'Xem lại →';
  } else if (state.orderStep === 2) {
    // Validate step 2
    const name = document.getElementById('order-name')?.value?.trim();
    const addr1 = document.getElementById('order-addr1')?.value?.trim();
    const city = document.getElementById('order-city')?.value?.trim();
    const state_val = document.getElementById('order-state')?.value?.trim();
    const postal = document.getElementById('order-postal')?.value?.trim();
    const country = document.getElementById('order-country')?.value?.trim();
    if (!name || !addr1 || !city || !state_val || !postal || !country) {
      showToast('Vui lòng điền đầy đủ thông tin giao hàng', 'error');
      return;
    }
    state.orderStep = 3;
    showOrderPreview();
    document.getElementById('order-step-1').style.display = 'none';
    document.getElementById('order-step-2').style.display = 'none';
    document.getElementById('order-step-3').style.display = 'block';
    document.getElementById('order-btn-next').textContent = '✅ Xác nhận tạo đơn';
  } else if (state.orderStep === 3) {
    submitOrder();
  }
}

function handleOrderPrev() {
  if (state.orderStep === 2) {
    state.orderStep = 1;
    document.getElementById('order-btn-prev').style.display = 'none';
    document.getElementById('order-btn-next').textContent = 'Tiếp theo →';
  } else if (state.orderStep === 3) {
    state.orderStep = 2;
    document.getElementById('order-step-1').style.display = 'block';
    document.getElementById('order-step-2').style.display = 'block';
    document.getElementById('order-step-3').style.display = 'none';
    document.getElementById('order-btn-next').textContent = 'Xem lại →';
  }
}

function showOrderPreview() {
  const preview = document.getElementById('order-preview');
  if (!preview) return;
  const sku = document.getElementById('order-sku')?.value?.trim() || '';
  const size = document.getElementById('order-size')?.value?.trim() || '';
  const qty = document.getElementById('order-qty')?.value || '1';
  const name = document.getElementById('order-name')?.value?.trim() || '';
  const email = document.getElementById('order-email')?.value?.trim() || '';
  const addr1 = document.getElementById('order-addr1')?.value?.trim() || '';
  const city = document.getElementById('order-city')?.value?.trim() || '';
  const state_val = document.getElementById('order-state')?.value?.trim() || '';
  const postal = document.getElementById('order-postal')?.value?.trim() || '';
  const country = document.getElementById('order-country')?.value?.trim() || '';

  preview.innerHTML = `
    <div class="order-preview-section">
      <h4>📦 Sản phẩm</h4>
      <table class="preview-table">
        <tr><td>SKU:</td><td><strong>${escapeHtml(sku)}</strong></td></tr>
        <tr><td>Size:</td><td>${escapeHtml(size)}</td></tr>
        <tr><td>Số lượng:</td><td>${escapeHtml(qty)}</td></tr>
      </table>
    </div>
    <div class="order-preview-section">
      <h4>🚚 Giao hàng</h4>
      <table class="preview-table">
        <tr><td>Tên:</td><td><strong>${escapeHtml(name)}</strong></td></tr>
        ${email ? `<tr><td>Email:</td><td>${escapeHtml(email)}</td></tr>` : ''}
        <tr><td>Địa chỉ:</td><td>${escapeHtml(addr1)}</td></tr>
        <tr><td>Thành phố:</td><td>${escapeHtml(city)}, ${escapeHtml(state_val)} ${escapeHtml(postal)}</td></tr>
        <tr><td>Quốc gia:</td><td>${escapeHtml(country)}</td></tr>
      </table>
    </div>
    <p class="preview-note">⚠️ Vui lòng kiểm tra kỹ trước khi xác nhận. Đơn hàng sau khi tạo sẽ được gửi đến BurgerPrints.</p>
  `;
}

async function submitOrder() {
  const sku = document.getElementById('order-sku')?.value?.trim() || '';
  const size = document.getElementById('order-size')?.value?.trim() || '';
  const qty = parseInt(document.getElementById('order-qty')?.value || '1', 10);
  const name = document.getElementById('order-name')?.value?.trim() || '';
  const email = document.getElementById('order-email')?.value?.trim() || '';
  const phone = document.getElementById('order-phone')?.value?.trim() || '';
  const addr1 = document.getElementById('order-addr1')?.value?.trim() || '';
  const addr2 = document.getElementById('order-addr2')?.value?.trim() || '';
  const city = document.getElementById('order-city')?.value?.trim() || '';
  const state_val = document.getElementById('order-state')?.value?.trim() || '';
  const postal = document.getElementById('order-postal')?.value?.trim() || '';
  const country = document.getElementById('order-country')?.value?.trim() || '';

  const payload = {
    sandbox: true,  // Dùng sandbox mode cho demo
    shipping: {
      name,
      email,
      phone,
      gift: false,
      address: {
        line1: addr1,
        line2: addr2,
        city,
        state: state_val,
        postal_code: postal,
        country,
      },
    },
    items: [{
      base_short_code: sku,
      size_name: size,
      quantity: qty,
    }],
  };

  try {
    const res = await fetch('/api/order/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    closeOrderModal();

    if (res.ok && data.success) {
      const orderId = data.order?.id || data.order?.data?.id || '';
      appendAssistantMessage(`✅ **Đơn hàng đã được tạo thành công!**\n\n- **Order ID:** \`${orderId}\`\n- **SKU:** ${sku}\n- **Size:** ${size} × ${qty}\n- **Giao cho:** ${name}\n- **Địa chỉ:** ${addr1}, ${city}, ${country}\n\nBurgerPrints sẽ bắt đầu xử lý đơn hàng của bạn.`, {
        intent: 'create_order',
        followUps: ['Kiểm tra trạng thái đơn hàng', 'Tìm thêm sản phẩm để bán'],
      });
    } else {
      const errMsg = data.error || 'Đã xảy ra lỗi không xác định';
      appendAssistantMessage(`❌ **Không thể tạo đơn hàng**\n\nLỗi: ${errMsg}\n\nVui lòng kiểm tra lại SKU và thông tin giao hàng.`, {
        intent: 'create_order',
        followUps: ['Thử tạo đơn lại', 'Kiểm tra SKU hợp lệ'],
        error: true,
      });
    }
  } catch (err) {
    closeOrderModal();
    console.error('Order submit error:', err);
    appendAssistantMessage('❌ Không thể kết nối để tạo đơn hàng. Vui lòng thử lại.', {
      intent: 'create_order',
      followUps: ['Thử lại'],
      error: true,
    });
  }
}

// ---------------------------------------------------------------------------
// API Status check
// ---------------------------------------------------------------------------

async function checkAPIStatus() {
  try {
    const response = await fetch('/api/balance/', { method: 'GET' });
    if (response.ok) {
      const data = await response.json();
      if (data.api_connected) {
        setStatus('online', 'API đã sẵn sàng');
      } else {
        setStatus('warning', 'API gặp vấn đề xác thực');
      }
    } else {
      setStatus('warning', 'API gặp vấn đề xác thực');
    }
  } catch {
    setStatus('error', 'Không kết nối được API');
  }
}

function setStatus(statusClass, label) {
  if (statusIndicator) {
    const color =
      statusClass === 'online' ? 'bg-emerald-500' :
      statusClass === 'warning' ? 'bg-amber-500' :
      statusClass === 'error' ? 'bg-red-500' :
      'bg-ink/30';
    statusIndicator.className = `h-2 w-2 rounded-full ${color}`;
  }
  if (statusLabel) statusLabel.textContent = label;
}

function setLoading(isLoading) {
  state.isLoading = isLoading;
  if (sendBtn) sendBtn.disabled = isLoading;
}

// ---------------------------------------------------------------------------
// Loading text by query type
// ---------------------------------------------------------------------------

function getLoadingText(query) {
  const q = query.toLowerCase();
  if (q.includes('so sánh') || q.includes('compare')) return 'Đang so sánh sản phẩm theo yêu cầu...';
  if (q.includes('tồn kho') || q.includes('còn hàng') || q.includes('hết hàng')) return 'Đang kiểm tra tình trạng tồn kho...';
  if (q.includes('partner') || q.includes('giá') || q.includes('$')) return 'Đang lọc catalog theo tiêu chí...';
  if (q.includes('đặt hàng') || q.includes('tạo đơn')) return 'Đang chuẩn bị thông tin đơn hàng...';
  return 'Đang phân tích và truy vấn BurgerPrints...';
}

// ---------------------------------------------------------------------------
// Intent label
// ---------------------------------------------------------------------------

function getIntentLabel(intent) {
  const map = {
    recommend_product: '🔍 Tìm sản phẩm',
    compare_product: '⚖️ So sánh',
    check_stock: '📦 Tồn kho',
    create_order: '📋 Tạo đơn',
    general_inquiry: '💬 Tư vấn',
  };
  return map[intent] || intent;
}

// ---------------------------------------------------------------------------
// Follow-up builder
// ---------------------------------------------------------------------------

function buildFollowUpsFromPayload(payload = {}) {
  if (Array.isArray(payload.follow_ups) && payload.follow_ups.length) {
    return payload.follow_ups;
  }

  const suggestions = [];
  const products = Array.isArray(payload.products) ? payload.products : [];
  const winner = payload.winner || products[0] || {};
  const second = products[1] || {};

  if (payload.intent === 'recommend_product') {
    if (winner.name) suggestions.push(`Phân tích kỹ hơn ${winner.name}`);
    if (winner.name && second.name) suggestions.push(`So sánh ${winner.name} với ${second.name}`);
    suggestions.push('Lọc tiếp theo màu, partner và ngân sách');
  } else if (payload.intent === 'compare_product') {
    suggestions.push('Cho tôi kết luận nên chọn sản phẩm nào');
    if (winner.name) suggestions.push(`Kiểm tra tồn kho cho ${winner.name}`);
    suggestions.push('So sánh thêm theo giá và partner');
  } else if (payload.intent === 'check_stock') {
    suggestions.push('Gợi ý sản phẩm thay thế tương tự');
    suggestions.push('Lọc sản phẩm còn hàng cho thị trường US');
  } else {
    suggestions.push('Tìm 3 sản phẩm dễ cho seller mới bán');
    suggestions.push('So sánh 2 sản phẩm theo giá và màu sắc');
    suggestions.push('Tìm sản phẩm dưới $12');
  }

  return [...new Set(suggestions)].slice(0, 4);
}

// ---------------------------------------------------------------------------
// Metadata → products list
// ---------------------------------------------------------------------------

function getProductsFromMessageMetadata(metadata = {}) {
  const scores = Array.isArray(metadata?.scores) ? metadata.scores : [];
  return scores.map((item) => {
    if (item.product) {
      return {
        ...item.product,
        score: item.score || 0,
        breakdown: item.breakdown || {},
        evidence: item.evidence || {},
      };
    }
    return item;
  }).filter(Boolean);
}

// ---------------------------------------------------------------------------
// Markdown rendering
// ---------------------------------------------------------------------------

function formatMarkdown(text) {
  if (!text) return '';
  if (typeof marked === 'undefined') {
    return `<p>${escapeHtml(text).replace(/\n/g, '<br>')}</p>`;
  }
  const rawHtml = marked.parse(text);
  return enhanceMarkdownHtml(sanitizeRenderedHtml(rawHtml));
}

function sanitizeRenderedHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  doc.querySelectorAll('script, style, iframe, object, embed').forEach((node) => node.remove());
  doc.querySelectorAll('*').forEach((node) => {
    [...node.attributes].forEach((attr) => {
      const name = attr.name.toLowerCase();
      const value = attr.value || '';
      if (name.startsWith('on')) node.removeAttribute(attr.name);
      if ((name === 'href' || name === 'src') && value.toLowerCase().startsWith('javascript:')) {
        node.removeAttribute(attr.name);
      }
    });
    if (node.tagName === 'A') {
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer');
    }
  });
  return doc.body.innerHTML;
}

function enhanceMarkdownHtml(html) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html;
  wrapper.querySelectorAll('table').forEach((table) => {
    const tableWrap = document.createElement('div');
    tableWrap.className = 'table-wrap';
    table.parentNode.insertBefore(tableWrap, table);
    tableWrap.appendChild(table);
  });
  return wrapper.innerHTML;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function escapeJs(str) {
  return String(str || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function scrollToBottom(smooth = true) {
  const target = chatScroll || messagesContainer;
  if (!target) return;
  target.scrollTo({
    top: target.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  });
}

function getCurrentTime() {
  return new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function formatHistoryTime(isoString) {
  if (!isoString) return getCurrentTime();
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return getCurrentTime();
  return date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i += 1) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === `${name}=`) {
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
  }, 3500);
}

function clearChat() {
  if (!messagesContainer) return;
  messagesContainer.innerHTML = '';
  hideProductCards();
  setActiveLayout(false);
}

function safeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseProcessingMin(product) {
  const explicit = safeNumber(product?.processing_min);
  if (explicit !== null) return explicit;
  const s = String(product?.processing_time || '');
  const range = s.match(/(\d+)\s*-\s*(\d+)/);
  if (range) return Number(range[1]);
  const single = s.match(/(\d+)/);
  if (single) return Number(single[1]);
  return null;
}

function deriveFactoriesFromProducts(products) {
  const byName = new Map();
  (products || []).forEach((p) => {
    const partners = Array.isArray(p?.partners) ? p.partners : [];
    partners.forEach((name) => {
      const key = String(name || '').trim();
      if (!key) return;

      const prev = byName.get(key) || {
        name: key,
        minBase: Infinity,
        avgScoreSum: 0,
        avgScoreCount: 0,
        processingMin: Infinity,
        processingLabel: null,
        locations: new Set(),
      };

      const priceMin = safeNumber(p?.price_min);
      if (priceMin !== null) prev.minBase = Math.min(prev.minBase, priceMin);

      const score = safeNumber(p?.score);
      if (score !== null) {
        prev.avgScoreSum += score;
        prev.avgScoreCount += 1;
      }

      const pm = parseProcessingMin(p);
      if (pm !== null && pm < prev.processingMin) {
        prev.processingMin = pm;
        prev.processingLabel = p?.processing_time || `${pm}d`;
      }

      const loc = String(p?.location || '').trim();
      if (loc) prev.locations.add(loc);

      byName.set(key, prev);
    });
  });

  const list = Array.from(byName.values()).map((f) => {
    const avg = f.avgScoreCount ? f.avgScoreSum / f.avgScoreCount : null;
    return {
      name: f.name,
      location: f.locations.size ? Array.from(f.locations).join(', ') : '—',
      baseCostValue: f.minBase !== Infinity ? f.minBase : null,
      baseCost: f.minBase !== Infinity ? `$${f.minBase.toFixed(2)}` : '—',
      productionTimeValue: f.processingMin !== Infinity ? f.processingMin : null,
      productionTime: f.processingLabel || '—',
      shippingTime: '—',
      qualityScoreValue: avg !== null ? avg : null,
      qualityScore: avg !== null ? `${Math.round(avg)} / 100` : '—',
      capacity: '—',
      avgScore: avg !== null ? avg : 0,
    };
  });

  list.sort((a, b) => {
    if (b.avgScore !== a.avgScore) return b.avgScore - a.avgScore;
    if ((a.baseCostValue ?? Infinity) !== (b.baseCostValue ?? Infinity)) return (a.baseCostValue ?? Infinity) - (b.baseCostValue ?? Infinity);
    return String(a.name).localeCompare(String(b.name));
  });

  return list.slice(0, 12);
}

function renderDecisionCanvas(payload) {
  if (!decisionTableBody || !decisionWinnerSubtitle || !decisionWinnerBase || !decisionWinnerProd || !decisionWinnerQuality || !decisionInsightsList || !decisionRankingCards) {
    return;
  }

  const products = Array.isArray(payload?.products) ? payload.products : [];
  const factories = deriveFactoriesFromProducts(products);
  const winner = factories[0] || null;

  if (winner) {
    decisionWinnerSubtitle.textContent = `${winner.name} — best overall trade-off (derived).`;
    decisionWinnerBase.textContent = winner.baseCost;
    decisionWinnerProd.textContent = winner.productionTime;
    decisionWinnerQuality.textContent = winner.qualityScore;
    if (decisionExportBtn) decisionExportBtn.disabled = false;
  } else {
    decisionWinnerSubtitle.textContent = 'Gửi một câu hỏi để hiển thị kết quả.';
    decisionWinnerBase.textContent = '—';
    decisionWinnerProd.textContent = '—';
    decisionWinnerQuality.textContent = '—';
    if (decisionExportBtn) decisionExportBtn.disabled = true;
  }

  decisionTableBody.innerHTML = '';
  factories.forEach((f, idx) => {
    const isWinner = idx === 0;
    const tr = document.createElement('tr');
    tr.className = isWinner ? 'bg-brandOrange/10 hover:bg-brandOrange/15 transition' : 'bg-white hover:bg-appBg/40 transition';
    tr.innerHTML = `
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}">
        <div class="flex items-center gap-2">
          <div class="font-${isWinner ? 'extrabold' : 'bold'}">${escapeHtml(f.name)}</div>
          ${isWinner ? `<span class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brandOrange text-white text-[11px] font-bold"><i class="fa-solid fa-trophy"></i> Winner</span>` : ''}
        </div>
        <div class="text-xs ${isWinner ? 'text-ink/70' : 'text-ink/60'}">${escapeHtml(f.location)}</div>
      </td>
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-extrabold' : 'border-black/5'}">${escapeHtml(f.baseCost)}</td>
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-semibold' : 'border-black/5'}">${escapeHtml(f.productionTime)}</td>
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}">${escapeHtml(f.shippingTime)}</td>
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-semibold' : 'border-black/5'}">${escapeHtml(f.qualityScore)}</td>
      <td class="py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}">${escapeHtml(f.capacity)}</td>
    `;
    decisionTableBody.appendChild(tr);
  });

  if (!factories.length) {
    const tr = document.createElement('tr');
    tr.className = 'bg-white';
    tr.innerHTML = `
      <td class="py-8 px-3 text-sm text-ink/60 border-b border-black/5" colspan="6">
        No factory-level data yet. Ask a question to populate the Decision Canvas.
      </td>
    `;
    decisionTableBody.appendChild(tr);
  }

  const lowest = [...factories].sort((a, b) => (a.baseCostValue ?? Infinity) - (b.baseCostValue ?? Infinity))[0] || null;
  const fastest = [...factories].sort((a, b) => (a.productionTimeValue ?? Infinity) - (b.productionTimeValue ?? Infinity))[0] || null;

  decisionInsightsList.innerHTML = `
    <li class="flex gap-2">
      <span class="mt-0.5 text-brandOrange"><i class="fa-solid fa-bolt"></i></span>
      <span><span class="font-semibold">Lowest Cost Factory:</span> ${lowest ? `${escapeHtml(lowest.name)} (${escapeHtml(lowest.baseCost)})` : '—'}</span>
    </li>
    <li class="flex gap-2">
      <span class="mt-0.5 text-brandOrange"><i class="fa-solid fa-bolt"></i></span>
      <span><span class="font-semibold">Fastest Production Factory:</span> ${fastest ? `${escapeHtml(fastest.name)} (${escapeHtml(fastest.productionTime)})` : '—'}</span>
    </li>
    <li class="flex gap-2">
      <span class="mt-0.5 text-brandOrange"><i class="fa-solid fa-bolt"></i></span>
      <span><span class="font-semibold">Best Overall Choice:</span> ${winner ? escapeHtml(winner.name) : '—'}</span>
    </li>
  `;

  decisionRankingCards.innerHTML = '';
  factories.slice(0, 3).forEach((f, i) => {
    const score = Math.max(0, Math.min(100, Math.round(f.avgScore || 0)));
    const card = document.createElement('div');
    card.className = 'rounded-xl border border-black/10 bg-white p-3 hover:shadow-sm transition';
    card.innerHTML = `
      <div class="flex items-start justify-between gap-2">
        <div>
          <div class="text-xs font-bold tracking-tight">#${i + 1} ${escapeHtml(f.name)}</div>
          <div class="text-[11px] text-ink/60 mt-0.5"><i class="fa-solid fa-location-dot text-brandOrange mr-1"></i> ${escapeHtml(f.location)}</div>
        </div>
        <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-appBg text-ink/70 text-[11px] font-semibold border border-black/10">
          <i class="fa-solid fa-gauge-high text-brandBlue"></i> ${score}/100
        </span>
      </div>
      <div class="mt-3 space-y-2 text-[11px] text-ink/70">
        <div class="flex items-center justify-between"><span>Base cost</span><span class="font-semibold">${escapeHtml(f.baseCost)}</span></div>
        <div class="flex items-center justify-between"><span>Production</span><span class="font-semibold">${escapeHtml(f.productionTime)}</span></div>
        <div class="flex items-center justify-between"><span>Quality</span><span class="font-semibold">${escapeHtml(f.qualityScore)}</span></div>
      </div>
      <div class="mt-3 h-2 rounded-full bg-appBg border border-black/5 overflow-hidden">
        <div class="h-full bg-brandBlue" style="width:${score}%"></div>
      </div>
    `;
    decisionRankingCards.appendChild(card);
  });

  if (decisionExportBtn) {
    decisionExportBtn.onclick = async () => {
      const snapshot = {
        session_id: state.sessionId,
        query: payload?.query || state.lastQuery || null,
        factories: factories.slice(0, 3).map((f) => ({
          factory: f.name,
          base_cost: f.baseCost,
          production_time: f.productionTime,
          quality_score: f.qualityScore,
          location: f.location,
        })),
      };
      try {
        await navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
        showToast('Đã copy snapshot', 'success');
      } catch {
        showToast('Không copy được snapshot', 'error');
      }
    };
  }
}
