/**
 * ClauseClear AI — Main Application JS
 * Handles: upload, unified analysis, risk cards, health gauge,
 * obligations table, loading stages, chat, toast, theme, CSRF.
 */

'use strict';

// ─── CSRF ──────────────────────────────────────────────────────────────────
function getCsrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function apiFetch(url, opts = {}) {
    opts.headers = Object.assign({ 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' }, opts.headers || {});
    return fetch(url, opts);
}

// ─── TOAST ─────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast--visible'));
    setTimeout(() => {
        toast.classList.remove('toast--visible');
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// ─── THEME ─────────────────────────────────────────────────────────────────
function initTheme() {
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    const applyTheme = (t) => {
        document.documentElement.setAttribute('data-theme', t);
        localStorage.setItem('theme', t);
        btn.textContent = t === 'dark' ? '☀️' : '🌙';
    };
    const current = localStorage.getItem('theme') || 'dark';
    applyTheme(current);
    btn.addEventListener('click', () => {
        applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
}

// ─── LOADING STAGES ────────────────────────────────────────────────────────
const LOAD_STAGES = [
    'Extracting document text…',
    'Classifying contract type…',
    'Applying Indian legal standard…',
    'Analyzing clauses against market benchmarks…',
    'Identifying obligations and deadlines…',
    'Calculating health score…',
    'Finalizing report…',
];

let _stageInterval = null;

function startLoading() {
    const loadEl = document.getElementById('results-loading');
    const emptyEl = document.getElementById('results-empty');
    const contentEl = document.getElementById('results-content');
    const errEl = document.getElementById('results-error');
    if (loadEl) loadEl.style.display = 'flex';
    if (emptyEl) emptyEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'none';
    if (errEl) errEl.style.display = 'none';

    let idx = 0;
    const stageEl = document.getElementById('loading-stage');
    const dots = document.querySelectorAll('.loading-stage-dot');
    const advance = () => {
        if (stageEl) stageEl.textContent = LOAD_STAGES[idx % LOAD_STAGES.length];
        dots.forEach((d, i) => d.classList.toggle('active', i === idx % dots.length));
        idx++;
    };
    advance();
    _stageInterval = setInterval(advance, 3000);
}

function stopLoading() {
    clearInterval(_stageInterval);
    const loadEl = document.getElementById('results-loading');
    if (loadEl) loadEl.style.display = 'none';
}

function showError(msg) {
    stopLoading();
    const errEl = document.getElementById('results-error');
    const errText = document.getElementById('error-text');
    if (errEl) errEl.style.display = 'flex';
    if (errText) errText.textContent = msg;
    showToast(msg, 'error');
}

// ─── HEALTH GAUGE ──────────────────────────────────────────────────────────
const GRADE_COLORS = { A: '#16a34a', B: '#14b8a6', C: '#eab308', D: '#f97316', F: '#ef4444' };

function renderHealthGauge(score, grade, verdict) {
    const section = document.getElementById('health-section');
    const fill = document.getElementById('gauge-fill');
    const scoreEl = document.getElementById('gauge-score');
    const gradeEl = document.getElementById('gauge-grade');
    const verdictEl = document.getElementById('health-verdict');
    if (!section) return;

    const circumference = 314;
    const offset = circumference - (score / 100) * circumference;
    const color = GRADE_COLORS[grade] || '#888';

    if (fill) { fill.style.strokeDashoffset = offset; fill.style.stroke = color; }
    if (scoreEl) scoreEl.textContent = score;
    if (gradeEl) { gradeEl.textContent = grade; gradeEl.style.color = color; }
    if (verdictEl) verdictEl.textContent = verdict || '';

    section.style.display = 'block';
}

// ─── CONTRACT TYPE BADGE ───────────────────────────────────────────────────
const TYPE_COLORS = {
    NDA: 'purple', EMPLOYMENT: 'blue', SAAS_TOS: 'cyan',
    FREELANCE: 'green', RENTAL: 'amber', LOAN: 'rose',
    PARTNERSHIP: 'indigo', UNKNOWN: 'gray',
};

function renderContractTypeBadge(contractType) {
    const badge = document.getElementById('contract-type-badge');
    if (!badge || !contractType) return;
    const color = TYPE_COLORS[contractType] || 'gray';
    badge.textContent = contractType;
    badge.className = `contract-type-badge badge-${contractType.toLowerCase()}`;
    badge.setAttribute('data-color', color);
    document.getElementById('results-meta').style.display = 'flex';
}

// ─── RISK CARDS ────────────────────────────────────────────────────────────
function renderRisks(risks) {
    const section = document.getElementById('risks-section');
    const container = document.getElementById('risk-cards');
    const breakdownEl = document.getElementById('risk-breakdown-badges');
    if (!section || !container) return;
    if (!risks || risks.length === 0) return;

    const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    risks.forEach(r => { if (counts[r.severity] !== undefined) counts[r.severity]++; });

    if (breakdownEl) {
        breakdownEl.innerHTML = Object.entries(counts).map(([sev, n]) =>
            `<span class="sev-badge sev-${sev.toLowerCase()}">${sev}: ${n}</span>`
        ).join('');
    }

    container.innerHTML = risks.map((risk, i) => {
        const sev = (risk.severity || 'LOW').toUpperCase();
        const clause = DOMPurify.sanitize(risk.clause || 'Unknown Clause');
        const explanation = DOMPurify.sanitize(risk.explanation || '');
        const redline = DOMPurify.sanitize(risk.suggested_redline || '');
        const sj = risk.standard_justification ? DOMPurify.sanitize(risk.standard_justification) : '';
        return `
        <div class="risk-card risk-card--${sev.toLowerCase()}">
            <span class="sev-pill sev-${sev.toLowerCase()}">${sev}</span>
            <h4 class="risk-clause">${clause}</h4>
            <p class="risk-explanation">${explanation}</p>
            ${sj ? `<div class="standard-justification">
                <span class="sj-label">⚖️ Legal Standard:</span>
                <span class="sj-text">${sj}</span>
            </div>` : ''}
            ${redline ? `
            <div class="redline-section">
                <button class="redline-toggle" onclick="toggleRedline(this)" aria-expanded="false">
                    💬 Negotiation Language <span class="toggle-arrow">▶</span>
                </button>
                <div class="redline-content" style="display:none;">
                    <p class="redline-text" id="redline-${i}">${redline}</p>
                    <button class="copy-btn" onclick="copyRedline('redline-${i}')">📋 Copy</button>
                </div>
            </div>` : ''}
        </div>`;
    }).join('');

    section.style.display = 'block';
}

function toggleRedline(btn) {
    const content = btn.nextElementSibling;
    const arrow = btn.querySelector('.toggle-arrow');
    const open = content.style.display !== 'none';
    content.style.display = open ? 'none' : 'block';
    if (arrow) arrow.textContent = open ? '▶' : '▼';
    btn.setAttribute('aria-expanded', !open);
}

function copyRedline(id) {
    const el = document.getElementById(id);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => showToast('Copied to clipboard!', 'success'));
}

// ─── OBLIGATIONS TABLE ─────────────────────────────────────────────────────
function renderObligations(obligations) {
    const section = document.getElementById('obligations-section');
    const tbody = document.getElementById('obligations-body');
    const emptyEl = document.getElementById('obligations-empty');
    if (!section || !tbody) return;

    if (!obligations || obligations.length === 0) {
        if (emptyEl) emptyEl.style.display = 'flex';
        section.style.display = 'block';
        return;
    }
    if (emptyEl) emptyEl.style.display = 'none';
    tbody.innerHTML = obligations.map((obl, i) => `
        <tr class="${i % 2 === 0 ? 'row-even' : 'row-odd'}">
            <td>${i + 1}</td>
            <td>${DOMPurify.sanitize(obl.obligation || '')}</td>
            <td>${DOMPurify.sanitize(obl.party || '')}</td>
            <td>${DOMPurify.sanitize(obl.deadline_description || '')}</td>
            <td>${DOMPurify.sanitize(obl.section || '')}</td>
        </tr>`).join('');
    section.style.display = 'block';
}

// ─── KEY ENTITIES ──────────────────────────────────────────────────────────
function renderEntities(keyEntities) {
    const section = document.getElementById('entities-section');
    const grid = document.getElementById('entities-grid');
    if (!section || !grid || !keyEntities) return;

    const parties = (keyEntities.parties || []).join(', ') || 'N/A';
    const items = [
        { label: '👥 Parties', value: parties },
        { label: '📅 Effective Date', value: keyEntities.effective_date || 'N/A' },
        { label: '⚖️ Governing Law', value: keyEntities.governing_law || 'N/A' },
        { label: '📢 Termination Notice', value: keyEntities.termination_notice || 'N/A' },
    ];
    grid.innerHTML = items.map(item => `
        <div class="entity-card">
            <div class="entity-label">${item.label}</div>
            <div class="entity-value">${DOMPurify.sanitize(String(item.value))}</div>
        </div>`).join('');
    section.style.display = 'block';
}

// ─── RENDER UNIFIED RESULT ─────────────────────────────────────────────────
let _currentAnalysisId = null;

function renderUnifiedResult(data) {
    stopLoading();
    const contentEl = document.getElementById('results-content');
    if (!contentEl) return;
    contentEl.style.display = 'block';

    _currentAnalysisId = data.analysis_id || null;

    const r = data.result || {};
    const contractType = r.contract_type || data.contract_type || 'UNKNOWN';

    renderContractTypeBadge(contractType);
    renderHealthGauge(r.health_score || 0, r.health_grade || 'F', r.health_verdict || '');

    // Summary
    const summaryBlock = document.getElementById('summary-block');
    const summaryText = document.getElementById('summary-text');
    if (r.summary && summaryText) {
        summaryText.textContent = r.summary;
        if (summaryBlock) summaryBlock.style.display = 'block';
    }

    renderEntities(r.key_entities || {});
    renderRisks(r.risks || []);
    renderObligations(r.obligations || []);

    // Export button
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn && _currentAnalysisId) {
        exportBtn.style.display = 'inline-flex';
        exportBtn.onclick = () => window.open(`/api/export/${_currentAnalysisId}`, '_blank');
    }

    // Show chat section
    const chatSection = document.getElementById('chat-section');
    if (chatSection) chatSection.style.display = 'block';
}

// ─── RENDER LEGACY RESULT ──────────────────────────────────────────────────
function renderLegacyResult(data, tabId) {
    stopLoading();
    const contentEl = document.getElementById('results-content');
    if (!contentEl) return;
    contentEl.style.display = 'block';

    const r = data.result || {};
    const label = DOMPurify.sanitize(data.feature_label || data.feature || '');
    const target = tabId ? document.getElementById(tabId) : document.getElementById('tab-panels-container');
    if (!target) return;

    let html = `<div class="legacy-result">`;
    if (!tabId) html += `<h3 class="section-heading">${label}</h3>`;

    // Feature-specific renderers
    if (r.highlighted_clauses) {
        html += renderHighlightHTML(r);
    } else if (r.clauses || r.quick_summary || r.sections) {
        if (r.quick_summary) html += `<p class="quick-summary">${DOMPurify.sanitize(r.quick_summary)}</p>`;
        
        const itemsToRender = r.clauses || r.sections;
        if (itemsToRender && itemsToRender.length) {
            html += itemsToRender.map(c => {
                const textSnippet = c.clause || c.original_clause || c.original_text_snippet || c.original_text || '';
                const plainLang = c.plain_language || c.plain_summary || '';
                const summaryText = c.summary || '';
                
                return `
                <div class="clause-card">
                    <div class="clause-tag-row">
                        ${(c.tags || []).map(t => `<span class="clause-tag">${DOMPurify.sanitize(t)}</span>`).join('')}
                    </div>
                    <p class="clause-text">${DOMPurify.sanitize(textSnippet)}</p>
                    ${plainLang ? `<p class="clause-plain">✏️ ${DOMPurify.sanitize(plainLang)}</p>` : ''}
                    ${summaryText ? `<p class="clause-plain">📋 ${DOMPurify.sanitize(summaryText)}</p>` : ''}
                </div>`;
            }).join('');
        }
    } else {
        html += `<pre class="json-dump">${DOMPurify.sanitize(JSON.stringify(r, null, 2))}</pre>`;
    }
    html += `</div>`;
    target.innerHTML = html;

    const chatSection = document.getElementById('chat-section');
    if (chatSection) chatSection.style.display = 'block';
}

function renderHighlightHTML(r) {
    const clauses = r.highlighted_clauses || [];
    const hrc = r.high_risk_count || clauses.filter(c => c.classification === 'HIGH_RISK').length;
    const rc  = r.risk_count     || clauses.filter(c => c.classification === 'RISK').length;
    const nc  = r.neutral_count  || clauses.filter(c => c.classification === 'NEUTRAL').length;
    const pc  = r.positive_count || clauses.filter(c => c.classification === 'POSITIVE').length;

    // Summary bar
    let html = `<div class="highlight-summary">`;
    if (hrc > 0) html += `<span class="hl-badge hl-high-risk">🚨 HIGH RISK: ${hrc}</span>`;
    html += `<span class="hl-badge hl-risk">⚠️ Risk: ${rc}</span>
        <span class="hl-badge hl-neutral">➖ Neutral: ${nc}</span>
        <span class="hl-badge hl-positive">✅ Positive: ${pc}</span>
    </div>`;

    // Overall verdict
    if (r.quick_summary) {
        html += `<p class="quick-summary">${DOMPurify.sanitize(r.quick_summary)}</p>`;
    }

    // Sort: HIGH_RISK first, then RISK, NEUTRAL, POSITIVE
    const ORDER = { HIGH_RISK: 0, RISK: 1, NEUTRAL: 2, POSITIVE: 3 };
    const sorted = [...clauses].sort((a, b) =>
        (ORDER[a.classification] ?? 9) - (ORDER[b.classification] ?? 9)
    );

    html += sorted.map((c, i) => {
        const cls   = (c.classification || 'NEUTRAL').toLowerCase().replace('_', '-');
        const isHigh = c.classification === 'HIGH_RISK';
        const icons  = { HIGH_RISK: '🚨', RISK: '⚠️', NEUTRAL: '➖', POSITIVE: '✅' };
        const icon   = icons[c.classification] || '➖';
        const tip    = c.negotiation_tip ? DOMPurify.sanitize(c.negotiation_tip) : '';
        const tipId  = `hl-tip-${i}`;
        const sj     = c.standard_justification ? DOMPurify.sanitize(c.standard_justification) : '';

        return `<div class="hl-clause hl-clause--${cls}${isHigh ? ' hl-clause--high-risk-card' : ''}">
            <div class="hl-clause-header">
                <span class="hl-cls-badge hl-cls--${cls}">${icon} ${c.classification?.replace('_', ' ')}</span>
            </div>
            <p class="hl-text">${DOMPurify.sanitize(c.text || '')}</p>
            <p class="hl-reason">${DOMPurify.sanitize(c.reason || '')}</p>
            ${sj ? `<div class="standard-justification">
                <span class="sj-label">⚖️ Legal Standard:</span>
                <span class="sj-text">${sj}</span>
            </div>` : ''}
            ${tip ? `<div class="hl-tip-row">
                <p class="hl-tip" id="${tipId}">💡 ${tip}</p>
                <button class="copy-btn" style="margin-top:4px;" onclick="navigator.clipboard.writeText(document.getElementById('${tipId}').textContent.replace('💡 ',''));showToast('Tip copied!','success')">📋 Copy Tip</button>
            </div>` : ''}
        </div>`;
    }).join('');

    return html;
}

// ─── ANALYZE (UNIFIED) ─────────────────────────────────────────────────────
async function runUnifiedAnalysis(contractText) {
    startLoading();
    try {
        const resp = await apiFetch('/api/analyze', {
            method: 'POST',
            body: JSON.stringify({ contract_text: contractText, evaluation_standard: document.getElementById('legal-standard')?.value || 'general_commercial' }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            showError(data.error || 'Analysis failed. Please try again.');
            return;
        }
        renderUnifiedResult(data);
        updateMemoryCount();
    } catch (e) {
        showError('A network error occurred. Please check your connection.');
    }
}

// ─── ANALYZE (FEATURE — single or tabbed) ─────────────────────────────────
async function runFeatureAnalysis(feature, contractText, extraContext = '', tabId = null) {
    if (!tabId) startLoading();
    try {
        const resp = await apiFetch('/api/analyze/feature', {
            method: 'POST',
            body: JSON.stringify({ feature, contract_text: contractText, extra_context: extraContext, evaluation_standard: document.getElementById('legal-standard')?.value || 'general_commercial' }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            if (tabId) {
                const el = document.getElementById(tabId);
                if (el) el.innerHTML = `<p class="quick-summary" style="color:var(--error)">❌ ${DOMPurify.sanitize(data.error || 'Failed')}</p>`;
            } else {
                showError(data.error || 'Analysis failed.');
            }
            return data;
        }
        renderLegacyResult(data, tabId);
        updateMemoryCount();
        return data;
    } catch (e) {
        if (!tabId) showError('A network error occurred.');
        return null;
    }
}

// ─── UPLOAD ────────────────────────────────────────────────────────────────
async function uploadFile(file) {
    const statusEl = document.getElementById('upload-status');
    const nameEl = document.getElementById('upload-filename');
    const charsEl = document.getElementById('upload-chars');
    const zoneEl = document.getElementById('upload-zone');

    if (zoneEl) zoneEl.classList.add('uploading');

    const fd = new FormData();
    fd.append('file', file);

    try {
        const resp = await fetch('/api/upload', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrf() },
            body: fd,
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            showToast(data.error || 'Upload failed.', 'error');
            return;
        }
        if (nameEl) nameEl.textContent = data.filename;
        if (charsEl) charsEl.textContent = `${data.char_count.toLocaleString()} chars`;
        if (statusEl) statusEl.style.display = 'block';
        showToast(data.message, 'success');
    } catch (e) {
        showToast('Upload failed. Please try again.', 'error');
    } finally {
        if (zoneEl) zoneEl.classList.remove('uploading');
    }
}

// ─── CHAT ──────────────────────────────────────────────────────────────────
async function sendChat(message) {
    const msgsEl = document.getElementById('chat-messages');
    if (!msgsEl) return;

    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble chat-bubble--user';
    userBubble.textContent = message;
    msgsEl.appendChild(userBubble);
    msgsEl.scrollTop = msgsEl.scrollHeight;

    try {
        const resp = await apiFetch('/api/chat', {
            method: 'POST',
            body: JSON.stringify({ message, analysis_id: _currentAnalysisId }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Chat request failed.', 'error');
            return;
        }
        const aiBubble = document.createElement('div');
        aiBubble.className = 'chat-bubble chat-bubble--ai';
        aiBubble.innerHTML = DOMPurify.sanitize(data.answer || data.error || 'No response.');
        msgsEl.appendChild(aiBubble);
        msgsEl.scrollTop = msgsEl.scrollHeight;
        updateMemoryCount();
    } catch (e) {
        showToast('Chat request failed.', 'error');
    }
}

// ─── MEMORY COUNT ──────────────────────────────────────────────────────────
function updateMemoryCount() {
    fetch('/api/memory')
        .then(r => r.json())
        .then(d => {
            const el = document.getElementById('memory-turns');
            if (el) el.textContent = d.turn_count || 0;
        })
        .catch(() => {});
}

// ─── MULTI-SELECT SYSTEM ───────────────────────────────────────────────────
const _selected = new Set();

function initMultiSelect() {
    document.querySelectorAll('.feature-btn[data-selectable]').forEach(btn => {
        btn.addEventListener('click', () => {
            const f = btn.dataset.feature;
            if (_selected.has(f)) {
                _selected.delete(f);
                btn.classList.remove('fb--selected');
            } else {
                _selected.add(f);
                btn.classList.add('fb--selected');
            }
            _updateRunBar();
        });
    });
    document.getElementById('run-selected-btn')?.addEventListener('click', _runSelected);
    document.getElementById('run-deselect-btn')?.addEventListener('click', () => {
        _selected.clear();
        document.querySelectorAll('.feature-btn[data-selectable]').forEach(b => b.classList.remove('fb--selected'));
        _updateRunBar();
    });
}

function _updateRunBar() {
    const bar = document.getElementById('run-selected-bar');
    const countEl = document.getElementById('run-selected-count');
    if (!bar) return;
    bar.style.display = _selected.size > 0 ? 'flex' : 'none';
    if (countEl) countEl.textContent = _selected.size;
}

async function _runSelected() {
    const contractText = document.getElementById('contract-text')?.value || '';
    const features = Array.from(_selected);
    if (!features.length) return;

    // Build tabs
    const tabBar = document.getElementById('results-tab-bar');
    const panels = document.getElementById('tab-panels-container');
    const contentEl = document.getElementById('results-content');
    const emptyEl = document.getElementById('results-empty');
    // Hide health/risk/obligations sections (those are for unified only)
    ['health-section','entities-section','risks-section','obligations-section'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    if (emptyEl) emptyEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';
    if (tabBar) { tabBar.style.display = 'flex'; tabBar.innerHTML = ''; }
    if (panels) panels.innerHTML = '';

    const LABELS = {
        summary_plain: '📋 Summary & Plain Language',
        tags: '🏷️ Tag Clauses',
        highlight: '🖊️ Clause Highlighter',
    };

    features.forEach((f, i) => {
        const tabId = `tab-panel-${f}`;
        // Tab button
        const tabBtn = document.createElement('button');
        tabBtn.className = `rtab-btn${i === 0 ? ' active' : ''}`;
        tabBtn.dataset.tab = tabId;
        tabBtn.textContent = LABELS[f] || f;
        tabBtn.addEventListener('click', () => {
            document.querySelectorAll('.rtab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.rtab-panel').forEach(p => p.style.display = 'none');
            tabBtn.classList.add('active');
            document.getElementById(tabId).style.display = 'block';
        });
        if (tabBar) tabBar.appendChild(tabBtn);
        // Panel
        const panel = document.createElement('div');
        panel.id = tabId;
        panel.className = 'rtab-panel';
        panel.style.display = i === 0 ? 'block' : 'none';
        panel.innerHTML = `<div class="tab-loading"><div class="loading-spinner-ring" style="width:32px;height:32px;"></div><span>Running ${LABELS[f] || f}…</span></div>`;
        if (panels) panels.appendChild(panel);
    });

    startLoading();
    // Run sequentially
    for (const f of features) {
        const tabId = `tab-panel-${f}`;
        if (f === 'summary_plain') {
            // Use apiFetch directly to avoid renderLegacyResult() being called with a null
            // tabId, which would overwrite tab-panels-container and destroy all tab panels.
            const evalStd = document.getElementById('legal-standard')?.value || 'general_commercial';
            const [sumResp, plainResp] = await Promise.all([
                apiFetch('/api/analyze/feature', {
                    method: 'POST',
                    body: JSON.stringify({ feature: 'summarize', contract_text: contractText, extra_context: '', evaluation_standard: evalStd }),
                }),
                apiFetch('/api/analyze/feature', {
                    method: 'POST',
                    body: JSON.stringify({ feature: 'translate', contract_text: contractText, extra_context: '', evaluation_standard: evalStd }),
                }),
            ]);
            const sumData  = sumResp.ok  ? await sumResp.json()  : null;
            const plainData = plainResp.ok ? await plainResp.json() : null;
            updateMemoryCount();

            const panel = document.getElementById(tabId);
            if (panel) {
                const sr = sumData?.result  || {};
                const pr = plainData?.result || {};
                const errMsg = (!sumResp.ok && sumData?.error) || (!plainResp.ok && plainData?.error);
                if (errMsg) {
                    panel.innerHTML = `<p class="quick-summary" style="color:var(--error)">❌ ${DOMPurify.sanitize(errMsg)}</p>`;
                } else {
                    let html = '<div class="legacy-result">';
                    if (sr.quick_summary) html += `<h4 class="er-heading">📋 Summary</h4><p class="quick-summary">${DOMPurify.sanitize(sr.quick_summary)}</p>`;
                    if (sr.clauses?.length) {
                        html += `<h4 class="er-heading">📑 Clause Summaries</h4>`;
                        html += sr.clauses.map(c => `<div class="clause-card"><p class="clause-text">${DOMPurify.sanitize(c.original_text_snippet || '')}</p><p class="clause-plain">📋 ${DOMPurify.sanitize(c.plain_summary || '')}</p></div>`).join('');
                    }
                    if (pr.sections?.length) {
                        html += `<h4 class="er-heading" style="margin-top:1.5rem;">✏️ Plain Language</h4>`;
                        html += pr.sections.map(c => `<div class="clause-card"><p class="clause-text">${DOMPurify.sanitize(c.original_text || '')}</p><p class="clause-plain">✏️ ${DOMPurify.sanitize(c.plain_language || '')}</p></div>`).join('');
                    }
                    html += '</div>';
                    panel.innerHTML = html;
                }
            }
        } else {
            await runFeatureAnalysis(f, contractText, '', tabId);
        }
    }
    stopLoading();
    const chatSection = document.getElementById('chat-section');
    if (chatSection) chatSection.style.display = 'block';
    showToast(`${features.length} analysis complete!`, 'success');
}

// ─── ANALYZE PAGE INIT ─────────────────────────────────────────────────────
function initAnalyzePage() {
    // Full Analysis — immediate run
    document.getElementById('btn-unified')?.addEventListener('click', async () => {
        const contractText = document.getElementById('contract-text')?.value || '';
        await runUnifiedAnalysis(contractText);
    });

    initMultiSelect();

    // Upload zone
    const zone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    if (zone && fileInput) {
        zone.addEventListener('click', () => fileInput.click());
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
        zone.addEventListener('drop', e => {
            e.preventDefault();
            zone.classList.remove('drag-over');
            const f = e.dataTransfer.files[0];
            if (f) uploadFile(f);
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) uploadFile(fileInput.files[0]);
        });
    }

    // Chat form
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    if (chatForm && chatInput) {
        chatForm.addEventListener('submit', async e => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;
            chatInput.value = '';
            await sendChat(msg);
        });
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
        });
    }

    document.getElementById('clear-memory-btn')?.addEventListener('click', () => {
        apiFetch('/api/clear-memory', { method: 'POST' })
            .then(() => { updateMemoryCount(); showToast('Memory cleared.', 'success'); });
    });

    updateMemoryCount();
}

// ─── GLOBAL INIT ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    // Nav mobile toggle
    document.getElementById('nav-toggle')?.addEventListener('click', () => {
        document.getElementById('nav-links')?.classList.toggle('open');
    });
});
