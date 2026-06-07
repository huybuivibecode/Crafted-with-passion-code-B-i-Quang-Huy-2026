import { useEffect, useMemo, useRef, useState } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const API_BASE = import.meta.env.VITE_API_BASE || ''

function getNowTime() {
  return new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
}

function formatHistoryTime(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return getNowTime()
  }
}

function safeNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function parseProcessingMin(product) {
  const n = safeNumber(product?.processing_min)
  if (n !== null && n > 0) return n
  const text = String(product?.processing_time || '')
  const m = text.match(/(\d+)\s*[-–]\s*(\d+)\s*(?:business\s*)?days?/i)
  if (m) return Number(m[1])
  const m2 = text.match(/within\s+(\d+)\s*(?:business\s*)?days?/i)
  if (m2) return Number(m2[1])
  return null
}

function deriveFactoriesFromProducts(products) {
  const byName = new Map()
    ; (products || []).forEach((p) => {
      const partners = Array.isArray(p?.partners) ? p.partners : []
      partners.forEach((partnerNameRaw) => {
        const key = String(partnerNameRaw || '').trim()
        if (!key) return
        const prev = byName.get(key) || {
          name: key,
          minBase: Infinity,
          avgScoreSum: 0,
          avgScoreCount: 0,
          processingMin: Infinity,
          processingLabel: null,
          locations: new Set(),
        }
        const priceMin = safeNumber(p?.price_min)
        if (priceMin !== null) prev.minBase = Math.min(prev.minBase, priceMin)
        const score = safeNumber(p?.score)
        if (score !== null) {
          prev.avgScoreSum += score
          prev.avgScoreCount += 1
        }
        const pm = parseProcessingMin(p)
        if (pm !== null && pm < prev.processingMin) {
          prev.processingMin = pm
          prev.processingLabel = p?.processing_time || `${pm}d`
        }
        const loc = String(p?.location || '').trim()
        if (loc) prev.locations.add(loc)
        byName.set(key, prev)
      })
    })

  const list = Array.from(byName.values()).map((f) => {
    const avg = f.avgScoreCount ? f.avgScoreSum / f.avgScoreCount : null
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
    }
  })

  list.sort((a, b) => {
    if (b.avgScore !== a.avgScore) return b.avgScore - a.avgScore
    if ((a.baseCostValue ?? Infinity) !== (b.baseCostValue ?? Infinity)) return (a.baseCostValue ?? Infinity) - (b.baseCostValue ?? Infinity)
    return String(a.name).localeCompare(String(b.name))
  })

  return list.slice(0, 12)
}

function buildPartnerColorMap(detail) {
  const variations = Array.isArray(detail?.variations) ? detail.variations : []
  const availableColors = Array.isArray(detail?.available_colors) ? detail.available_colors : []
  const colorHexByName = new Map()

  availableColors.forEach((c) => {
    if (!c) return
    if (typeof c === 'string') {
      colorHexByName.set(String(c).trim().toLowerCase(), '')
      return
    }
    if (typeof c === 'object') {
      const name = String(c.name || '').trim()
      const hex = String(c.color_hex || '').trim()
      if (name) colorHexByName.set(name.toLowerCase(), hex)
    }
  })

  const byPartner = new Map()
  variations.forEach((v) => {
    if (!v || typeof v !== 'object') return
    const partner = String(v.partner_name || v.partner || '').trim()
    const colorName = String(v.color || '').trim()
    let hex = String(v.color_hex || '').trim()
    if (!hex && colorName) hex = String(colorHexByName.get(colorName.toLowerCase()) || '').trim()
    if (!partner || !hex) return
    if (!byPartner.has(partner)) byPartner.set(partner, new Map())
    const key = hex.toLowerCase()
    if (!byPartner.get(partner).has(key)) {
      byPartner.get(partner).set(key, { name: colorName, hex })
    }
  })

  const entries = Array.from(byPartner.entries())
    .map(([partner, colorsMap]) => [partner, Array.from(colorsMap.values())])
    .sort((a, b) => (b[1].length - a[1].length) || String(a[0]).localeCompare(String(b[0])))

  return Object.fromEntries(entries)
}

function getProductsFromMessageMetadata(metadata) {
  const scores = Array.isArray(metadata?.scores) ? metadata.scores : []
  return scores
    .map((s) => (s && typeof s === 'object' ? s : null))
    .filter(Boolean)
}

function App() {
  const chatPanelRef = useRef(null)
  const canvasPanelRef = useRef(null)
  const scrollRef = useRef(null)

  const [sessionId, setSessionId] = useState(() => {
    const saved = localStorage.getItem('bp_session_id')
    if (saved) return saved
    const id = crypto.randomUUID()
    localStorage.setItem('bp_session_id', id)
    return id
  })
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [statusLabel, setStatusLabel] = useState('Đang kết nối...')
  const [statusKind, setStatusKind] = useState('loading')
  const [products, setProducts] = useState([])
  const [lastQuery, setLastQuery] = useState('')
  const [toast, setToast] = useState({ visible: false, message: '', kind: 'info' })
  const [showProductSuggestions, setShowProductSuggestions] = useState(true)
  const [showPartnerColors, setShowPartnerColors] = useState(true)
  const [splitPct, setSplitPct] = useState(() => Number(localStorage.getItem('bp_split_pct') || 40))
  const [minimized, setMinimized] = useState(() => localStorage.getItem('bp_minimized') || 'none')
  const [chatWidth, setChatWidth] = useState(null)
  const [canvasWidth, setCanvasWidth] = useState(null)

  const [partnerColorsOpen, setPartnerColorsOpen] = useState(false)
  const [partnerColorsTitle, setPartnerColorsTitle] = useState('')
  const [partnerColorsMap, setPartnerColorsMap] = useState({})
  const [partnerColorsLoading, setPartnerColorsLoading] = useState(false)
  const [colorPreviewHex, setColorPreviewHex] = useState('')
  const [showTip, setShowTip] = useState(true)

  const partnerColorCacheRef = useRef({})

  const isActive = messages.length > 0
  const isSplitMode = isActive && minimized === 'none'
  const isChatHidden = isActive && minimized === 'chat'
  const isCanvasHidden = isActive && minimized === 'canvas'

  const isChatCompact = isSplitMode && typeof chatWidth === 'number' && chatWidth > 0 && chatWidth < 520
  const isCanvasCompact = isSplitMode && typeof canvasWidth === 'number' && canvasWidth > 0 && canvasWidth < 980

  const formatMarkdown = useMemo(() => {
    marked.setOptions({ breaks: true })
    return (text) => {
      const raw = marked.parse(String(text || ''))
      return DOMPurify.sanitize(raw)
    }
  }, [])

  const factories = useMemo(() => deriveFactoriesFromProducts(products), [products])
  const winnerFactory = factories[0] || null
  const lowestFactory = useMemo(() => [...factories].sort((a, b) => (a.baseCostValue ?? Infinity) - (b.baseCostValue ?? Infinity))[0] || null, [factories])
  const fastestFactory = useMemo(() => [...factories].sort((a, b) => (a.productionTimeValue ?? Infinity) - (b.productionTimeValue ?? Infinity))[0] || null, [factories])

  function showToast(message, kind = 'info') {
    setToast({ visible: true, message, kind })
    window.clearTimeout(showToast._t)
    showToast._t = window.setTimeout(() => setToast((t) => ({ ...t, visible: false })), 2400)
  }

  async function apiFetch(path, init) {
    const res = await fetch(`${API_BASE}${path}`, init)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const msg = data?.error || 'request_failed'
      throw new Error(msg)
    }
    return data
  }

  async function checkAPIStatus() {
    try {
      await apiFetch('/api/cache/stats/', { method: 'GET' })
      setStatusKind('ok')
      setStatusLabel('Đang hoạt động')
    } catch {
      setStatusKind('error')
      setStatusLabel('Mất kết nối')
    }
  }

  async function loadHistory(id) {
    try {
      const data = await apiFetch(`/api/history/${encodeURIComponent(id)}/`, { method: 'GET' })
      const list = Array.isArray(data?.messages) ? data.messages : []
      if (!list.length) return

      const next = []
      let lastAssistantProducts = []
      list.forEach((m) => {
        if (m?.role === 'user') {
          next.push({
            id: `m_${m.id}`,
            role: 'user',
            content: m.content || '',
            createdAt: m.created_at,
            fromHistory: true,
          })
          return
        }
        const derivedProducts = getProductsFromMessageMetadata(m?.metadata)
        next.push({
          id: `m_${m.id}`,
          role: 'assistant',
          content: m.content || '',
          intent: m.intent || '',
          metadata: m.metadata || {},
          createdAt: m.created_at,
          fromHistory: true,
        })
        if (derivedProducts.length) lastAssistantProducts = derivedProducts
      })
      setMessages(next)
      if (lastAssistantProducts.length) setProducts(lastAssistantProducts)
    } catch {
    }
  }

  function persistSplit(pct) {
    localStorage.setItem('bp_split_pct', String(pct))
  }

  function persistMinimized(mode) {
    localStorage.setItem('bp_minimized', mode)
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n))
  }

  function applySplit(pct) {
    const p = clamp(Number(pct) || 40, 28, 72)
    if (chatPanelRef.current) chatPanelRef.current.style.flexBasis = `${p}%`
    if (canvasPanelRef.current) canvasPanelRef.current.style.flexBasis = `${100 - p}%`
  }

  function updateMinimized(mode, { persist = true } = {}) {
    const m = ['none', 'chat', 'canvas'].includes(mode) ? mode : 'none'
    setMinimized(m)
    if (persist) persistMinimized(m)
    if (!chatPanelRef.current || !canvasPanelRef.current) return

    if (m === 'chat') {
      chatPanelRef.current.style.display = 'none'
      canvasPanelRef.current.style.display = 'flex'
      canvasPanelRef.current.style.flexBasis = '100%'
      return
    }
    if (m === 'canvas') {
      canvasPanelRef.current.style.display = 'none'
      chatPanelRef.current.style.display = 'flex'
      chatPanelRef.current.style.flexBasis = '100%'
      return
    }
    chatPanelRef.current.style.display = 'flex'
    canvasPanelRef.current.style.display = 'flex'
    applySplit(splitPct)
  }

  useEffect(() => {
    checkAPIStatus()
    loadHistory(sessionId)
  }, [sessionId])

  useEffect(() => {
    if (!isActive) return
    if (minimized === 'none') applySplit(splitPct)
  }, [isActive])

  useEffect(() => {
    if (!isActive) return
    if (minimized !== 'none') return
    applySplit(splitPct)
  }, [splitPct, minimized, isActive])

  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isLoading])

  useEffect(() => {
    if (!isActive) return
    const chatEl = chatPanelRef.current
    const canvasEl = canvasPanelRef.current
    if (!chatEl || !canvasEl) return
    if (typeof ResizeObserver === 'undefined') return

    const ro = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        const id = entry?.target?.id
        const w = entry?.contentRect?.width
        if (!Number.isFinite(w)) return
        if (id === 'bp-chat-panel') setChatWidth(w)
        if (id === 'bp-canvas-panel') setCanvasWidth(w)
      })
    })
    ro.observe(chatEl)
    ro.observe(canvasEl)
    return () => ro.disconnect()
  }, [isActive])

  async function handleSend(forcedText = '') {
    const query = String(forcedText || input || '').trim()
    if (!query || isLoading) return

    setLastQuery(query)
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: query, createdAt: new Date().toISOString() },
    ])
    setInput('')
    setIsLoading(true)

    try {
      const data = await apiFetch('/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionId }),
      })
      const resp = String(data?.response || '')
      const assistant = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: resp || 'Xin lỗi, mình chưa tạo được câu trả lời phù hợp.',
        intent: data?.intent || '',
        metadata: {
          reasons: data?.reasons || [],
          winner: data?.winner || {},
          alternatives: data?.alternatives || [],
          scores: data?.products || [],
        },
        createdAt: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistant])
      setProducts(Array.isArray(data?.products) ? data.products : [])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `❌ Không thể kết nối tới server.\n\n- Lỗi: ${String(e?.message || 'unknown')}`,
          intent: 'general_inquiry',
          createdAt: new Date().toISOString(),
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  async function handleClearCache() {
    try {
      await apiFetch('/api/cache/stats/', { method: 'DELETE' })
      showToast('Đã refresh cache', 'success')
    } catch {
      showToast('Không refresh được cache', 'error')
    }
  }

  function handleNewChat() {
    const id = crypto.randomUUID()
    localStorage.setItem('bp_session_id', id)
    setSessionId(id)
    setMessages([])
    setProducts([])
    setLastQuery('')
    setInput('')
    partnerColorCacheRef.current = {}
    updateMinimized('none', { persist: true })
    showToast('Đã tạo phiên mới', 'success')
  }

  async function openPartnerColors(productId, productName) {
    if (!productId || !showPartnerColors) return
    setPartnerColorsOpen(true)
    setPartnerColorsTitle(`🎨 Màu theo partner — ${productName ? `${productName} (${productId})` : productId}`)
    setPartnerColorsLoading(true)
    setPartnerColorsMap({})
    try {
      if (partnerColorCacheRef.current[productId]) {
        setPartnerColorsMap(partnerColorCacheRef.current[productId])
        return
      }
      const detail = await apiFetch(`/api/products/${encodeURIComponent(productId)}/`, { method: 'GET' })
      const map = buildPartnerColorMap(detail)
      partnerColorCacheRef.current[productId] = map
      setPartnerColorsMap(map)
    } catch {
      setPartnerColorsMap({})
    } finally {
      setPartnerColorsLoading(false)
    }
  }

  function copyToClipboard(text) {
    const value = String(text || '')
    navigator.clipboard.writeText(value).then(
      () => showToast('Đã copy', 'success'),
      () => showToast('Không copy được', 'error'),
    )
  }

  function onResizerPointerDown(e) {
    if (!isActive || minimized !== 'none') return
    const startX = e.clientX
    const start = splitPct
    let current = start
    const onMove = (ev) => {
      const dx = ev.clientX - startX
      const shell = document.getElementById('bp-shell')
      const w = shell ? shell.getBoundingClientRect().width : window.innerWidth
      const next = clamp(start + (dx / w) * 100, 28, 72)
      current = next
      setSplitPct(next)
      applySplit(next)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      persistSplit(current)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  useEffect(() => {
    if (!isActive) return
    if (minimized === 'none') {
      updateMinimized('none', { persist: false })
      return
    }
    updateMinimized(minimized, { persist: false })
  }, [isActive])

  const statusDotClass = statusKind === 'ok' ? 'bg-emerald-500' : statusKind === 'warning' ? 'bg-amber-500' : statusKind === 'error' ? 'bg-red-500' : 'bg-ink/30'

  return (
    <div id="app">
      <main className="h-screen overflow-hidden">
        <div id="bp-shell" className="h-full flex flex-col lg:flex-row gap-4 p-4 transition-all">
          <section
            id="bp-chat-panel"
            ref={chatPanelRef}
            className={`min-w-0 h-full rounded-2xl bg-white shadow-soft border border-black/5 overflow-hidden flex flex-col transition-all duration-500 ease-out ${isActive ? 'lg:basis-2/5' : 'lg:basis-full'} ${isChatHidden ? 'hidden' : ''}`}
            aria-label="AI chat panel"
          >
            <header className={`${isChatCompact ? 'px-4 py-3' : 'px-5 py-4'} border-b border-black/5 bg-white`}>
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-10 w-10 rounded-xl bg-appBg border border-black/10 overflow-hidden flex items-center justify-center">
                    <div className="items-center justify-center h-full w-full text-xs font-semibold text-ink/70 flex">BP</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-lg sm:text-xl font-extrabold tracking-tight leading-tight truncate">
                      <span className="text-brandBlue">BURGER</span>
                      <span className="text-brandOrange">PRINTS</span>
                      <span className="text-ink">Agent</span>
                    </div>
                    <div className={`${isChatCompact ? 'hidden' : 'block'} text-xs text-ink/60 mt-0.5`}>
                      AI Agent giúp seller POD tìm, so sánh, tối ưu fulfillment.
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleClearCache}
                    type="button"
                    className="hidden sm:inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition"
                    title="Làm mới catalog từ API"
                  >
                    <i className="fa-solid fa-arrows-rotate text-ink/60"></i> {isChatCompact ? null : 'Refresh'}
                  </button>

                  <button
                    onClick={handleNewChat}
                    type="button"
                    className="hidden sm:inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition"
                    title="Tạo phiên mới"
                  >
                    <i className="fa-solid fa-plus text-ink/60"></i> {isChatCompact ? null : 'New'}
                  </button>

                  <button
                    onClick={() => updateMinimized(minimized === 'chat' ? 'none' : 'chat', { persist: true })}
                    type="button"
                    className={`hidden lg:inline-flex items-center justify-center h-10 w-10 rounded-xl bg-white border border-black/10 text-ink/70 hover:bg-appBg transition ${isActive ? '' : 'opacity-50 pointer-events-none'}`}
                    title={minimized === 'chat' ? 'Hiện lại chia đôi' : 'Ẩn pane trái'}
                  >
                    <i className={`fa-solid ${minimized === 'chat' ? 'fa-up-right-and-down-left-from-center' : 'fa-window-minimize'}`}></i>
                  </button>

                  <span className="inline-flex items-center gap-2 px-3 py-2 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">
                    <span className={`h-2 w-2 rounded-full ${statusDotClass}`}></span>
                    <span>{statusLabel}</span>
                  </span>
                </div>
              </div>
            </header>



            <div
              id="bp-chat-scroll"
              ref={scrollRef}
              className={`flex-1 overflow-y-auto nice-scrollbar ${isChatCompact ? 'px-4 py-4' : 'px-5 py-5'} bg-gradient-to-b from-white to-appBg/60`}
            >
              {!isActive ? (
                <section id="bp-landing" className="min-h-[calc(100vh-220px)] flex items-center justify-center" aria-label="Landing experience">
                  <div className="w-full max-w-3xl text-center">
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-black/10 text-xs font-semibold text-ink/70 shadow-sm">
                      <i className="fa-solid fa-wand-magic-sparkles text-brandOrange"></i>
                      Premium AI SaaS Workflow
                    </div>

                    <h1 className="mt-5 text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight leading-tight">
                      Find the Perfect SKU. <span className="text-brandBlue">Faster.</span>
                    </h1>
                    <p className="mt-4 text-base sm:text-lg text-ink/65">
                      Ask BurgerPrintsAgent to compare factories, optimize fulfillment, and discover the best product options.
                    </p>

                    <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
                      {[
                        {
                          icon: 'fa-magnifying-glass',
                          color: 'brandBlue',
                          prompt: 'Find US-based Hoodie factories with under 3-day production time.',
                          meta: 'Filters: US • Hoodie • ≤ 3 days',
                        },
                        {
                          icon: 'fa-chart-column',
                          color: 'brandOrange',
                          prompt: 'Compare T-shirt base costs and shipping rates between top factories.',
                          meta: 'Compare: base cost • shipping',
                        },
                        {
                          icon: 'fa-bolt',
                          color: 'brandBlue',
                          prompt: 'Optimize EU fulfillment routes to reduce delivery delays.',
                          meta: 'Optimize: EU routes • lead time',
                        },
                        {
                          icon: 'fa-dollar-sign',
                          color: 'brandOrange',
                          prompt: 'Find the most profitable T-shirt under $8 base cost.',
                          meta: 'Constraint: base cost < $8',
                        },
                      ].map((x) => {
                        const iconBoxClass = x.color === 'brandOrange'
                          ? 'h-10 w-10 rounded-xl bg-brandOrange/10 text-brandOrange flex items-center justify-center border border-brandOrange/15 shrink-0'
                          : 'h-10 w-10 rounded-xl bg-brandBlue/10 text-brandBlue flex items-center justify-center border border-brandBlue/15 shrink-0'
                        return (
                          <button
                            key={x.prompt}
                            className="group rounded-2xl bg-white border border-black/10 shadow-sm hover:shadow-soft transition p-4"
                            onClick={() => handleSend(x.prompt)}
                            type="button"
                          >
                            <div className="flex items-start gap-3">
                              <div className={iconBoxClass}>
                                <i className={`fa-solid ${x.icon}`}></i>
                              </div>
                              <div>
                                <div className="text-sm font-bold group-hover:text-brandBlue transition">
                                  {x.prompt}
                                </div>
                                <div className="mt-1 text-xs text-ink/55">{x.meta}</div>
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {showTip ? (
                    <div className="mt-6 mx-auto max-w-2xl flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 shadow-sm">
                      <i className="fa-solid fa-lightbulb text-amber-500 mt-0.5 shrink-0"></i>
                      <span className="flex-1 leading-relaxed text-left">
                        <span className="font-semibold">Mẹo để đảm bảo độ chính xác:</span> Nhấn{' '}
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 border border-amber-300 font-semibold">
                          <i className="fa-solid fa-arrows-rotate text-[10px]"></i> Refresh
                        </span>{' '}
                        để cập nhật dữ liệu catalog mới nhất, sau đó nhấn{' '}
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 border border-amber-300 font-semibold">
                          <i className="fa-solid fa-plus text-[10px]"></i> New
                        </span>{' '}
                        để tạo phiên chat mới trước khi hỏi.
                      </span>
                      <button
                        type="button"
                        onClick={() => setShowTip(false)}
                        className="shrink-0 text-amber-400 hover:text-amber-600 transition ml-1"
                        title="Đóng"
                      >
                        <i className="fa-solid fa-xmark"></i>
                      </button>
                    </div>
                  ) : null}
                </section>
              ) : null}

              {isActive ? (
                <div id="messages-container" className="space-y-4" aria-label="Chat messages">
                  {messages.map((m) => (
                    m.role === 'user' ? (
                      <div className="flex justify-end" key={m.id}>
                        <div className="max-w-[92%] sm:max-w-[80%]">
                          <div className="rounded-2xl rounded-tr-sm bg-brandBlue text-white px-4 py-3 shadow-sm">
                            <div className="text-sm leading-relaxed">{m.content}</div>
                          </div>
                          <div className="mt-1 text-[11px] text-ink/50 text-right">
                            {m.fromHistory ? formatHistoryTime(m.createdAt) : formatHistoryTime(m.createdAt)}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex justify-start" key={m.id}>
                        <div className="max-w-[96%] sm:max-w-[86%]">
                          <div className="flex items-start gap-3">
                            <div className="h-9 w-9 rounded-xl bg-white border border-black/10 shadow-sm flex items-center justify-center shrink-0">
                              <i className="fa-solid fa-robot text-ink/70"></i>
                            </div>
                            <div className="rounded-2xl rounded-tl-sm bg-white border border-black/5 px-4 py-3 shadow-sm w-full">
                              <div className="flex items-center justify-between gap-3 flex-wrap">
                                <div className="flex items-center gap-2 flex-wrap">
                                  {m.intent ? (
                                    <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">
                                      {m.intent}
                                    </span>
                                  ) : null}
                                  {m.fromHistory ? (
                                    <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white text-ink/60 text-xs font-semibold border border-black/10">
                                      <i className="fa-solid fa-clock-rotate-left text-ink/40"></i> Lịch sử
                                    </span>
                                  ) : null}
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition"
                                    onClick={() => copyToClipboard(m.content)}
                                    type="button"
                                    title="Sao chép"
                                  >
                                    <i className="fa-solid fa-copy text-ink/60"></i> Copy
                                  </button>
                                </div>
                              </div>

                              <div className="prose prose-sm max-w-none mt-3 text-ink/80" dangerouslySetInnerHTML={{ __html: formatMarkdown(m.content) }}></div>
                            </div>
                          </div>
                          <div className="mt-1 text-[11px] text-ink/50">{m.fromHistory ? formatHistoryTime(m.createdAt) : getNowTime()}</div>
                        </div>
                      </div>
                    )
                  ))}

                  {isLoading ? (
                    <div className="flex justify-start">
                      <div className="max-w-[96%] sm:max-w-[86%]">
                        <div className="flex items-start gap-3">
                          <div className="h-9 w-9 rounded-xl bg-white border border-black/10 shadow-sm flex items-center justify-center shrink-0">
                            <i className="fa-solid fa-robot text-ink/70"></i>
                          </div>
                          <div className="rounded-2xl rounded-tl-sm bg-white border border-black/5 px-4 py-3 shadow-sm">
                            <div className="text-sm text-ink/60">Đang xử lý...</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {products.length ? (
                <div id="product-cards-area" className="mt-6">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-bold">🏆 Sản phẩm gợi ý</div>
                      <div className="text-xs text-ink/60 mt-0.5">{products.length} sản phẩm</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        className={`px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition ${showProductSuggestions ? '' : 'active'}`}
                        onClick={() => setShowProductSuggestions((s) => !s)}
                        type="button"
                      >
                        {showProductSuggestions ? 'Ẩn gợi ý' : 'Hiện gợi ý'}
                      </button>
                      <button
                        className={`px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition ${showPartnerColors ? '' : 'active'}`}
                        onClick={() => setShowPartnerColors((s) => !s)}
                        type="button"
                      >
                        {showPartnerColors ? 'Ẩn màu theo partner' : 'Hiện màu theo partner'}
                      </button>
                    </div>
                  </div>

                  {showProductSuggestions ? (
                    <div id="product-cards-grid" className={`mt-3 grid ${isChatCompact ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3'} gap-3 ${showPartnerColors ? '' : 'partner-colors-hidden'}`}>
                      {products.map((p, idx) => {
                        const id = p.id || p.short_code || ''
                        const min = safeNumber(p.price_min)
                        const max = safeNumber(p.price_max)
                        const baseStr = min !== null
                          ? (max !== null && max > min ? `$${min.toFixed(2)}–$${max.toFixed(2)}` : `$${min.toFixed(2)}`)
                          : ''
                        const partners = Array.isArray(p.partners) ? p.partners.filter(Boolean) : []
                        const partnerText = partners.length ? partners.slice(0, 3).join(', ') : ''
                        const morePartners = partners.length > 3 ? ` (+${partners.length - 3})` : ''
                        return (
                          <div
                            key={id || idx}
                            className="rounded-2xl border border-black/10 bg-white p-4 hover:shadow-sm transition"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-start gap-3 min-w-0">
                                {p.thumbnail ? (
                                  <img className="h-12 w-12 rounded-xl object-cover border border-black/10" src={p.thumbnail} alt={p.name || ''} />
                                ) : (
                                  <div className="h-12 w-12 rounded-xl bg-appBg border border-black/10 flex items-center justify-center text-ink/50">
                                    <i className="fa-solid fa-shirt"></i>
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <div className="text-xs font-bold text-ink/60">#{idx + 1}</div>
                                  <div className="text-sm font-extrabold leading-tight truncate" title={p.name || ''}>{p.name || 'N/A'}</div>
                                  <div className="text-xs text-ink/60 font-mono mt-0.5">{p.short_code || p.id || ''}</div>
                                  {baseStr ? (
                                    <div className="text-xs text-ink/60 mt-1">Base: <span className="font-semibold text-ink">{baseStr}</span></div>
                                  ) : null}
                                  {partnerText ? (
                                    <div className="text-xs text-ink/60 mt-1"><i className="fa-solid fa-industry text-brandOrange mr-1"></i> {partnerText}{morePartners}</div>
                                  ) : null}
                                </div>
                              </div>
                              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/10">
                                <i className="fa-solid fa-gauge-high text-brandBlue"></i> {Math.round(safeNumber(p.score) || 0)}/100
                              </span>
                            </div>

                            <div className="mt-3 flex items-center justify-between gap-2">
                              <button
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition"
                                onClick={() => openPartnerColors(id, p.name || '')}
                                type="button"
                                disabled={!showPartnerColors}
                              >
                                <i className="fa-solid fa-palette text-brandOrange"></i> {isChatCompact ? null : 'Màu theo partner'}
                              </button>
                              <button
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-brandBlue text-white text-xs font-semibold hover:brightness-110 active:brightness-95 transition"
                                onClick={() => handleSend(`Phân tích kỹ hơn ${p.name || p.short_code || ''}`)}
                                type="button"
                              >
                                <i className="fa-solid fa-magnifying-glass"></i> {isChatCompact ? null : 'Phân tích'}
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className={`border-t border-black/5 bg-white ${isCanvasHidden ? '' : ''}`} id="bp-input-area">
              <div className="p-4">
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-2" id="composer-suggestions">
                    <button className="composer-chip px-3 py-2 rounded-xl bg-appBg border border-black/10 text-xs font-semibold hover:bg-white transition" onClick={() => handleSend('So sánh các factory/partner theo giá, thời gian sản xuất và chất lượng')} type="button">Factory Comparison</button>
                    <button className="composer-chip px-3 py-2 rounded-xl bg-appBg border border-black/10 text-xs font-semibold hover:bg-white transition" onClick={() => handleSend('Gợi ý sản phẩm POD phù hợp nhất cho tôi')} type="button">Product recommend</button>
                  </div>

                  <div className="flex items-end gap-2">
                    <button type="button" className="h-11 w-11 rounded-xl border border-black/10 bg-white hover:bg-appBg transition flex items-center justify-center text-ink/70" title="Upload">
                      <i className="fa-solid fa-paperclip"></i>
                    </button>
                    <button type="button" className="h-11 w-11 rounded-xl border border-black/10 bg-white hover:bg-appBg transition flex items-center justify-center text-ink/70" title="Voice">
                      <i className="fa-solid fa-microphone"></i>
                    </button>

                    <div className="flex-1">
                      <div className="relative">
                        <textarea
                          id="chat-input"
                          className="w-full min-h-[44px] max-h-40 rounded-xl border border-black/10 bg-appBg/40 px-4 py-3 pr-14 text-sm outline-none focus:ring-4 focus:ring-brandBlue/15 focus:border-brandBlue/40 resize-none"
                          placeholder="Nhắn tin tự nhiên như đang chat..."
                          rows="1"
                          maxLength={500}
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault()
                              handleSend()
                            }
                          }}
                        />
                        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                          <span className="text-ink/35 text-[11px] font-semibold">{(input || '').length}/500</span>
                        </div>
                      </div>
                    </div>

                    <button
                      className="h-11 px-4 rounded-xl bg-brandBlue text-white font-semibold text-sm shadow-sm hover:brightness-110 active:brightness-95 transition disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => handleSend()}
                      disabled={isLoading || !(input || '').trim()}
                      type="button"
                      title="Gửi (Enter)"
                    >
                      <i className="fa-solid fa-paper-plane mr-2"></i> Send
                    </button>
                  </div>

                  <div className="text-[11px] text-ink/50">Enter để gửi · Shift+Enter xuống dòng · lịch sử giữ theo session</div>
                </div>
              </div>
            </div>
          </section>

          <div
            id="bp-resizer"
            className={`hidden lg:flex h-full w-2 items-center justify-center cursor-col-resize select-none ${isSplitMode ? '' : 'hidden'}`}
            onPointerDown={onResizerPointerDown}
          >
            <div className="h-20 w-1 rounded-full bg-black/10"></div>
          </div>

          <section
            id="bp-canvas-panel"
            ref={canvasPanelRef}
            className={`${isActive && !isCanvasHidden ? 'flex' : 'hidden'} min-w-0 h-full rounded-2xl bg-white shadow-soft border border-black/5 overflow-hidden flex-col transition-all duration-500 ease-out lg:basis-3/5`}
            aria-label="Decision canvas panel"
          >
            <header className="px-5 pt-5 pb-4 border-b border-black/5 bg-white">
              <div className="flex items-start justify-between gap-3">
                <div className="hidden sm:flex items-center gap-2">
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg text-ink/70 text-xs font-semibold border border-black/5">
                    <i className="fa-solid fa-shield-halved text-brandOrange"></i> Data-backed picks
                  </span>
                  <button
                    onClick={() => updateMinimized(minimized === 'canvas' ? 'none' : 'canvas', { persist: true })}
                    id="bp-min-canvas-btn"
                    type="button"
                    className="hidden lg:inline-flex items-center justify-center h-10 w-10 rounded-xl bg-white border border-black/10 text-ink/70 hover:bg-appBg transition"
                    title={minimized === 'canvas' ? 'Hiện lại chia đôi' : 'Ẩn pane phải'}
                  >
                    <i className={`fa-solid ${minimized === 'canvas' ? 'fa-up-right-and-down-left-from-center' : 'fa-window-minimize'}`}></i>
                  </button>
                </div>
              </div>
            </header>

            <div className="flex-1 overflow-y-auto nice-scrollbar bg-gradient-to-b from-white to-appBg/60 p-5" id="bp-canvas-content">
              <div className={isCanvasCompact ? 'grid grid-cols-1 gap-4' : 'grid grid-cols-1 xl:grid-cols-3 gap-4'}>
                <div className="xl:col-span-1 rounded-2xl bg-white border border-black/5 shadow-sm p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold">Best Overall Choice</div>
                      <div className="text-sm text-ink/60 mt-1">{winnerFactory ? `${winnerFactory.name} — best overall trade-off (derived).` : 'Gửi một câu hỏi để hiển thị kết quả.'}</div>
                    </div>
                    <div className="h-10 w-10 rounded-xl bg-brandOrange text-white flex items-center justify-center shadow-sm">
                      <i className="fa-solid fa-trophy"></i>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    <div className="rounded-xl bg-appBg/60 border border-black/5 p-3">
                      <div className="text-[11px] text-ink/60">Base</div>
                      <div className="text-sm font-extrabold">{winnerFactory ? winnerFactory.baseCost : '—'}</div>
                    </div>
                    <div className="rounded-xl bg-appBg/60 border border-black/5 p-3">
                      <div className="text-[11px] text-ink/60">Production</div>
                      <div className="text-sm font-extrabold">{winnerFactory ? winnerFactory.productionTime : '—'}</div>
                    </div>
                    <div className="rounded-xl bg-appBg/60 border border-black/5 p-3">
                      <div className="text-[11px] text-ink/60">Quality</div>
                      <div className="text-sm font-extrabold">{winnerFactory ? winnerFactory.qualityScore : '—'}</div>
                    </div>
                  </div>
                </div>

                <div className="xl:col-span-2 rounded-2xl bg-white border border-black/5 shadow-sm p-4 overflow-hidden">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold">Factory Table</div>
                      <div className="text-sm text-ink/60 mt-1">Derived from the latest candidate products.</div>
                    </div>
                    <button
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-black/10 text-xs font-semibold hover:bg-appBg transition disabled:opacity-50"
                      type="button"
                      disabled={!factories.length}
                      onClick={() => {
                        const snapshot = {
                          session_id: sessionId,
                          query: lastQuery || null,
                          factories: factories.slice(0, 3).map((f) => ({
                            factory: f.name,
                            base_cost: f.baseCost,
                            production_time: f.productionTime,
                            quality_score: f.qualityScore,
                            location: f.location,
                          })),
                        }
                        copyToClipboard(JSON.stringify(snapshot, null, 2))
                      }}
                    >
                      <i className="fa-solid fa-download text-ink/60"></i> Export
                    </button>
                  </div>

                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-ink/60">
                          <th className="py-2 px-3">Factory</th>
                          <th className="py-2 px-3">Base</th>
                          <th className="py-2 px-3">Production</th>
                          <th className="py-2 px-3">Shipping</th>
                          <th className="py-2 px-3">Quality</th>
                          <th className="py-2 px-3">Capacity</th>
                        </tr>
                      </thead>
                      <tbody>
                        {factories.length ? factories.map((f, idx) => {
                          const isWinner = idx === 0
                          return (
                            <tr key={f.name} className={isWinner ? 'bg-brandOrange/10 hover:bg-brandOrange/15 transition' : 'bg-white hover:bg-appBg/40 transition'}>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}`}>
                                <div className="flex items-center gap-2">
                                  <div className={isWinner ? 'font-extrabold' : 'font-bold'}>{f.name}</div>
                                  {isWinner ? (
                                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brandOrange text-white text-[11px] font-bold"><i className="fa-solid fa-trophy"></i> Winner</span>
                                  ) : null}
                                </div>
                                <div className={`text-xs ${isWinner ? 'text-ink/70' : 'text-ink/60'}`}>{f.location}</div>
                              </td>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-extrabold' : 'border-black/5'}`}>{f.baseCost}</td>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-semibold' : 'border-black/5'}`}>{f.productionTime}</td>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}`}>{f.shippingTime}</td>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20 font-semibold' : 'border-black/5'}`}>{f.qualityScore}</td>
                              <td className={`py-3 px-3 border-b ${isWinner ? 'border-brandOrange/20' : 'border-black/5'}`}>{f.capacity}</td>
                            </tr>
                          )
                        }) : (
                          <tr className="bg-white">
                            <td className="py-8 px-3 text-sm text-ink/60 border-b border-black/5" colSpan={6}>
                              No factory-level data yet. Ask a question to populate the Decision Canvas.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <section className="xl:col-span-1 rounded-2xl bg-white border border-black/5 shadow-sm p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold">Insights</div>
                      <div className="text-sm text-ink/60 mt-1">Key takeaways from the latest run.</div>
                    </div>
                    <div className="h-10 w-10 rounded-xl bg-appBg border border-black/10 flex items-center justify-center text-ink/70">
                      <i className="fa-solid fa-lightbulb"></i>
                    </div>
                  </div>
                  <ul className="mt-4 space-y-2 text-sm text-ink/75">
                    <li className="flex gap-2">
                      <span className="mt-0.5 text-brandOrange"><i className="fa-solid fa-bolt"></i></span>
                      <span><span className="font-semibold">Lowest Cost Factory:</span> {lowestFactory ? `${lowestFactory.name} (${lowestFactory.baseCost})` : '—'}</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-0.5 text-brandOrange"><i className="fa-solid fa-bolt"></i></span>
                      <span><span className="font-semibold">Fastest Production Factory:</span> {fastestFactory ? `${fastestFactory.name} (${fastestFactory.productionTime})` : '—'}</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-0.5 text-brandOrange"><i className="fa-solid fa-bolt"></i></span>
                      <span><span className="font-semibold">Best Overall Choice:</span> {winnerFactory ? winnerFactory.name : '—'}</span>
                    </li>
                  </ul>
                </section>

                <section className="xl:col-span-2 rounded-2xl bg-white border border-black/5 shadow-sm p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold">Top Recommendations</div>
                      <div className="text-sm text-ink/60 mt-1">Top 3 factory options with score breakdown.</div>
                    </div>
                    <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-brandOrange/10 text-brandOrange text-xs font-semibold border border-brandOrange/20">
                      <i className="fa-solid fa-award"></i> Ranked
                    </span>
                  </div>
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {factories.slice(0, 3).map((f, i) => {
                      const score = Math.max(0, Math.min(100, Math.round(f.avgScore || 0)))
                      return (
                        <div key={f.name} className="rounded-xl border border-black/10 bg-white p-3 hover:shadow-sm transition">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="text-xs font-bold tracking-tight">#{i + 1} {f.name}</div>
                              <div className="text-[11px] text-ink/60 mt-0.5"><i className="fa-solid fa-location-dot text-brandOrange mr-1"></i> {f.location}</div>
                            </div>
                            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-appBg text-ink/70 text-[11px] font-semibold border border-black/10">
                              <i className="fa-solid fa-gauge-high text-brandBlue"></i> {score}/100
                            </span>
                          </div>
                          <div className="mt-3 space-y-2 text-[11px] text-ink/70">
                            <div className="flex items-center justify-between"><span>Base cost</span><span className="font-semibold">{f.baseCost}</span></div>
                            <div className="flex items-center justify-between"><span>Production</span><span className="font-semibold">{f.productionTime}</span></div>
                            <div className="flex items-center justify-between"><span>Quality</span><span className="font-semibold">{f.qualityScore}</span></div>
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-appBg border border-black/5 overflow-hidden">
                            <div className="h-full bg-brandBlue" style={{ width: `${score}%` }}></div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>
              </div>
            </div>

            <footer className="px-5 py-3 border-t border-black/5 bg-white" id="bp-canvas-footer">
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 justify-between">
                <div className="text-xs text-ink/60">
                  <span className="font-semibold">BurgerPrintsAgent</span> • AI Chat + Factory Decision Canvas
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-appBg border border-black/5 text-ink/70">
                    <i className="fa-solid fa-lock text-brandOrange"></i> Secure by design
                  </span>
                </div>
              </div>
            </footer>
          </section>
        </div>
      </main>

      {toast.visible ? (
        <div className="toast" style={{ display: 'block' }}>
          {toast.message}
        </div>
      ) : (
        <div className="toast" style={{ display: 'none' }}></div>
      )}

      <div className="modal-overlay" style={{ display: partnerColorsOpen ? 'flex' : 'none' }} onClick={(e) => { if (e.target?.classList?.contains('modal-overlay')) setPartnerColorsOpen(false) }}>
        <div className="partner-colors-card">
          <div className="partner-colors-header">
            <div className="partner-colors-title">{partnerColorsTitle}</div>
            <button className="modal-close" type="button" onClick={() => setPartnerColorsOpen(false)}>✕</button>
          </div>
          <div className="partner-colors-body">
            {partnerColorsLoading ? (
              <div className="mini-partners-text">Đang tải màu theo partner…</div>
            ) : (
              (() => {
                const partners = Object.keys(partnerColorsMap || {})
                if (!partners.length) return <div className="mini-partners-text">Chưa có dữ liệu màu theo partner cho sản phẩm này.</div>
                return (
                  <div className="space-y-4">
                    {partners.map((partner) => {
                      const colors = Array.isArray(partnerColorsMap[partner]) ? partnerColorsMap[partner] : []
                      return (
                        <div key={partner} className="partner-row">
                          <div className="partner-row-header">
                            <div className="partner-row-title">{partner}</div>
                            <div className="partner-row-count">{colors.length} màu</div>
                          </div>
                          <div className="swatch-row">
                            {colors.slice(0, 60).map((c) => {
                              const hex = String(c?.hex || '').trim()
                              if (!hex) return null
                              return (
                                <button
                                  key={`${partner}_${hex}`}
                                  className="color-swatch"
                                  type="button"
                                  style={{ background: hex }}
                                  title={hex}
                                  onClick={() => setColorPreviewHex(hex)}
                                ></button>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })()
            )}
          </div>
        </div>
      </div>

      <div className="modal-overlay" style={{ display: colorPreviewHex ? 'flex' : 'none' }} onClick={(e) => { if (e.target?.classList?.contains('modal-overlay')) setColorPreviewHex('') }}>
        <div className="color-preview-card">
          <div className="color-preview-header">
            <div className="color-preview-title">🎨 Màu sắc</div>
            <button className="modal-close" type="button" onClick={() => setColorPreviewHex('')}>✕</button>
          </div>
          <div className="color-preview-body">
            <div className="color-preview-swatch" style={{ background: colorPreviewHex }}></div>
            <div className="color-preview-hex">{String(colorPreviewHex || '').toUpperCase()}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
