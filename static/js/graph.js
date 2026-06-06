/**
 * BurgerPrintsAgent - Graph Visualization
 * ReactFlow-based workflow graph with execution tracing
 */

const { useState, useCallback, useEffect, useRef } = React;

// reactflow@11 UMD exports everything on window.ReactFlow
const RF = window.ReactFlow;
const ReactFlowComponent = RF.ReactFlow || RF.default;
const Background = RF.Background;
const Controls = RF.Controls;
const MiniMap = RF.MiniMap;
const Handle = RF.Handle;
const useNodesState = RF.useNodesState;
const useEdgesState = RF.useEdgesState;

// Position and MarkerType are enums, not exported in UMD — define manually
const Position = { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' };
const MarkerType = { Arrow: 'arrow', ArrowClosed: 'arrowclosed' };

// GRAPH_DEF is injected by the Django template as a global variable

// ── Custom Node Component ──
function CustomNode({ data }) {
  const { label, type, method, status, duration_ms, summary } = data;

  const classes = [
    'rf-custom-node',
    'type-' + type,
    status ? 'status-' + status : '',
  ].filter(Boolean).join(' ');

  const handleStyle = { background: '#555' };

  return React.createElement('div', { className: classes, title: summary || label },
    React.createElement(Handle, { type: 'target', position: Position.Top, style: handleStyle }),
    React.createElement('div', { className: 'rf-node-label' }, label),
    method ? React.createElement('div', { className: 'rf-node-method ' + method }, method) : null,
    typeof duration_ms === 'number'
      ? React.createElement('div', { className: 'rf-node-timing' }, duration_ms + 'ms')
      : null,
    React.createElement(Handle, { type: 'source', position: Position.Bottom, style: handleStyle })
  );
}

const nodeTypes = { custom: CustomNode };

// ── Build initial nodes & edges ──
function buildInitialNodes() {
  return window.GRAPH_DEF.nodes.map(function(n) {
    return {
      id: n.id,
      type: 'custom',
      position: { x: n.x, y: n.y },
      data: {
        label: n.label,
        type: n.type,
        method: null,
        status: null,
        duration_ms: null,
        summary: '',
      },
    };
  });
}

function buildInitialEdges() {
  return window.GRAPH_DEF.edges.map(function(e, i) {
    return {
      id: 'e-' + i,
      source: e.source,
      target: e.target,
      label: e.label || '',
      animated: false,
      style: { stroke: '#30363D', strokeWidth: 2 },
      labelStyle: { fill: '#8B949E', fontSize: 10 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#30363D' },
    };
  });
}

// ── Helpers ──
function getCookie(name) {
  var val = null;
  if (document.cookie) {
    document.cookie.split(';').forEach(function(c) {
      c = c.trim();
      if (c.startsWith(name + '=')) {
        val = decodeURIComponent(c.substring(name.length + 1));
      }
    });
  }
  return val;
}

function escapeHtml(str) {
  var div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

// ── Show node detail panel ──
function showNodeDetail(nodeId, trace) {
  var panel = document.getElementById('node-detail');
  var titleEl = document.getElementById('detail-title');
  var metaEl = document.getElementById('detail-meta');
  var outputEl = document.getElementById('detail-output');
  if (!panel || !titleEl || !metaEl || !outputEl) return;

  // Find trace entry
  var entry = null;
  for (var i = 0; i < trace.length; i++) {
    if (trace[i].node_id === nodeId) { entry = trace[i]; break; }
  }
  if (!entry) {
    panel.style.display = 'none';
    return;
  }

  // Title
  titleEl.textContent = entry.label;

  // Meta
  var statusIcon = entry.status === 'success' ? '✅' : '❌';
  metaEl.innerHTML =
    '<span>' + statusIcon + ' ' + entry.status + '</span>' +
    '<span>⚙ ' + entry.method + '</span>' +
    '<span>⏱ ' + entry.duration_ms + 'ms</span>' +
    (entry.desc ? '<span>📝 ' + escapeHtml(entry.desc) + '</span>' : '');

  // Output — pretty print JSON
  var output = entry.output || {};
  var formatted = '';
  try {
    formatted = JSON.stringify(output, null, 2);
  } catch (e) {
    formatted = String(output);
  }

  // Syntax highlight the JSON
  formatted = formatted
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"([^"]+)":/g, '<span style="color:#7C3AED">"$1"</span>:')
    .replace(/: "(.*?)"/g, ': <span style="color:#22D3EE">"$1"</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span style="color:#FCD34D">$1</span>')
    .replace(/: (true|false)/g, ': <span style="color:#22C55E">$1</span>')
    .replace(/: (null)/g, ': <span style="color:#8B949E">$1</span>');

  outputEl.innerHTML = formatted;

  // Show panel with animation
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Main App ──
function GraphApp() {
  var _ns = useNodesState(buildInitialNodes());
  var nodes = _ns[0], setNodes = _ns[1], onNodesChange = _ns[2];

  var _es = useEdgesState(buildInitialEdges());
  var edges = _es[0], setEdges = _es[1], onEdgesChange = _es[2];

  var _trace = useState([]);
  var trace = _trace[0], setTrace = _trace[1];

  var _running = useState(false);
  var isRunning = _running[0], setIsRunning = _running[1];

  var _resp = useState('');
  var response = _resp[0], setResponse = _resp[1];

  var _active = useState(null);
  var activeNodeId = _active[0], setActiveNodeId = _active[1];

  // Apply trace to nodes
  var applyTrace = useCallback(function(traceData) {
    var traceMap = {};
    traceData.forEach(function(t) { traceMap[t.node_id] = t; });

    var executedNodeIds = new Set(traceData.map(function(t) { return t.node_id; }));
    executedNodeIds.add('start');
    executedNodeIds.add('end');

    setNodes(function(prev) {
      return prev.map(function(n) {
        var t = traceMap[n.id];
        if (t) {
          return Object.assign({}, n, {
            data: Object.assign({}, n.data, {
              method: t.method,
              status: t.status,
              duration_ms: t.duration_ms,
              summary: t.summary,
            }),
          });
        }
        if (n.id === 'start' || n.id === 'end') {
          return Object.assign({}, n, {
            data: Object.assign({}, n.data, { status: 'success' }),
          });
        }
        if (!executedNodeIds.has(n.id)) {
          return Object.assign({}, n, {
            data: Object.assign({}, n.data, { status: 'skipped', method: null, duration_ms: null, summary: '' }),
          });
        }
        return n;
      });
    });

    setEdges(function(prev) {
      return prev.map(function(e) {
        var srcOk = executedNodeIds.has(e.source);
        var tgtOk = executedNodeIds.has(e.target);
        if (srcOk && tgtOk) {
          return Object.assign({}, e, {
            animated: true,
            style: { stroke: '#22D3EE', strokeWidth: 2.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#22D3EE' },
          });
        }
        return Object.assign({}, e, {
          animated: false,
          style: { stroke: '#30363D', strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#30363D' },
        });
      });
    });
  }, [setNodes, setEdges]);

  // Reset
  var resetGraph = useCallback(function() {
    setNodes(buildInitialNodes());
    setEdges(buildInitialEdges());
    setTrace([]);
    setResponse('');
    setActiveNodeId(null);
  }, [setNodes, setEdges]);

  // Run query
  var handleRun = useCallback(function() {
    var input = document.getElementById('graph-query');
    var query = input && input.value ? input.value.trim() : '';
    if (!query || isRunning) return;

    setIsRunning(true);
    resetGraph();

    var previewEl = document.getElementById('response-preview');
    var respContent = document.getElementById('response-content');
    if (previewEl) previewEl.classList.remove('show');

    var sessionId = '';
    var sidEl = document.getElementById('session-id-input');
    if (sidEl) sessionId = sidEl.value;

    fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ query: query, session_id: sessionId }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var traceData = data.node_trace || [];
      setTrace(traceData);
      applyTrace(traceData);

      if (data.response) {
        setResponse(data.response);
        if (previewEl) previewEl.classList.add('show');
        if (respContent) {
          var text = data.response;
          respContent.textContent = text.length > 400 ? text.substring(0, 400) + '...' : text;
        }
      }
    })
    .catch(function(err) {
      console.error('Graph run error:', err);
    })
    .finally(function() {
      setIsRunning(false);
    });
  }, [isRunning, resetGraph, applyTrace]);

  // Keyboard: Enter to run
  useEffect(function() {
    var input = document.getElementById('graph-query');
    function handler(e) {
      if (e.key === 'Enter') handleRun();
    }
    if (input) input.addEventListener('keydown', handler);
    return function() { if (input) input.removeEventListener('keydown', handler); };
  }, [handleRun]);

  // Button click
  useEffect(function() {
    var btn = document.getElementById('run-btn');
    function handler() { handleRun(); }
    if (btn) btn.addEventListener('click', handler);
    return function() { if (btn) btn.removeEventListener('click', handler); };
  }, [handleRun]);

  // Button state
  useEffect(function() {
    var btn = document.getElementById('run-btn');
    if (btn) {
      btn.disabled = isRunning;
      btn.textContent = isRunning ? '⏳ Running...' : '▶ Run';
    }
  }, [isRunning]);

  // Render trace list
  useEffect(function() {
    var traceList = document.getElementById('trace-list');
    var traceEmpty = document.getElementById('trace-empty');
    if (!traceList) return;

    if (trace.length === 0) {
      traceList.innerHTML = '';
      if (traceEmpty) traceEmpty.style.display = 'block';
      return;
    }
    if (traceEmpty) traceEmpty.style.display = 'none';

    var totalMs = trace.reduce(function(acc, t) { return acc + (t.duration_ms || 0); }, 0);

    var html = trace.map(function(t) {
      var isActive = activeNodeId === t.node_id ? 'active' : '';
      var summaryHtml = t.summary ? '<div class="trace-summary">' + escapeHtml(t.summary) + '</div>' : '';
      var errorHtml = t.error ? '<div class="trace-error-msg">⚠ ' + escapeHtml(t.error) + '</div>' : '';
      return '<div class="trace-item ' + isActive + '" data-node="' + t.node_id + '">' +
        '<div class="trace-row">' +
          '<div class="trace-status ' + t.status + '"></div>' +
          '<div class="trace-label">' + t.label + '</div>' +
          '<span class="trace-method ' + t.method + '">' + t.method + '</span>' +
          '<span class="trace-timing">' + t.duration_ms + 'ms</span>' +
        '</div>' +
        summaryHtml + errorHtml +
      '</div>';
    }).join('');

    html += '<div class="trace-total">' +
      '<span class="trace-total-label">Total</span>' +
      '<span class="trace-total-value">' + totalMs + 'ms</span>' +
    '</div>';

    traceList.innerHTML = html;

    traceList.querySelectorAll('.trace-item').forEach(function(item) {
      item.addEventListener('click', function() {
        var nodeId = item.dataset.node;
        setActiveNodeId(nodeId);
        showNodeDetail(nodeId, trace);
      });
    });
  }, [trace, activeNodeId]);

  // Close detail panel on button click
  useEffect(function() {
    var closeBtn = document.getElementById('detail-close');
    function handler() {
      var panel = document.getElementById('node-detail');
      if (panel) panel.style.display = 'none';
      setActiveNodeId(null);
    }
    if (closeBtn) closeBtn.addEventListener('click', handler);
    return function() { if (closeBtn) closeBtn.removeEventListener('click', handler); };
  }, []);

  // Render
  var minimapNodeColor = function(n) {
    if (n.data && n.data.status === 'success') return '#22C55E';
    if (n.data && n.data.status === 'error') return '#EF4444';
    if (n.data && n.data.status === 'skipped') return '#30363D';
    return '#8B949E';
  };

  return React.createElement(ReactFlowComponent, {
    nodes: nodes,
    edges: edges,
    onNodesChange: onNodesChange,
    onEdgesChange: onEdgesChange,
    nodeTypes: nodeTypes,
    onNodeClick: function(event, node) {
      setActiveNodeId(node.id);
      showNodeDetail(node.id, trace);
    },
    fitView: true,
    fitViewOptions: { padding: 0.2 },
    proOptions: { hideAttribution: true },
  },
    React.createElement(Background, { color: '#30363D', gap: 20, size: 1 }),
    React.createElement(Controls, null),
    React.createElement(MiniMap, {
      nodeColor: minimapNodeColor,
      style: { background: '#161B22' },
    })
  );
}

// ── Mount ──
document.addEventListener('DOMContentLoaded', function() {
  var container = document.getElementById('graph-canvas');
  if (container && ReactDOM.createRoot) {
    var root = ReactDOM.createRoot(container);
    root.render(React.createElement(GraphApp, null));
  }
});
