/**
 * ClauseClear AI — Frontend JavaScript
 * Handles file upload, 4 analysis modes, result rendering, and follow-up chat.
 */

// ─────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // ── Theme toggle ──────────────────────────────────────
    const themeBtn = document.getElementById('theme-toggle-btn');
    const THEME_KEY = 'clauseclear-theme';

    // Apply saved theme immediately (prevents flash)
    const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
    applyTheme(savedTheme);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const current = document.body.getAttribute('data-theme') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            localStorage.setItem(THEME_KEY, next);
        });
    }

    function applyTheme(theme) {
        document.body.setAttribute('data-theme', theme);
        if (themeBtn) themeBtn.textContent = theme === 'dark' ? '☀️' : '🌙';
    }

    // ── Nav mobile toggle ─────────────────────────────────
    const navToggle = document.getElementById('nav-toggle');
    const navLinks = document.getElementById('nav-links');
    if (navToggle && navLinks) {
        navToggle.addEventListener('click', () => navLinks.classList.toggle('open'));
    }
});

// ─────────────────────────────────────────────
// Analyze Page Init
// ─────────────────────────────────────────────

function initAnalyzePage() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const featureBtns = document.querySelectorAll('.feature-btn');
    const clearMemBtn = document.getElementById('clear-memory-btn');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');

    if (!uploadZone) return;

    // File upload — click
    uploadZone.addEventListener('click', () => fileInput.click());

    // File upload — drag & drop
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) uploadFile(fileInput.files[0]);
    });

    // Feature buttons
    featureBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            featureBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            runAnalysis(btn.dataset.feature);
        });
    });

    // Clear memory
    if (clearMemBtn) {
        clearMemBtn.addEventListener('click', clearMemory);
    }

    // Chat form
    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (msg) { sendChat(msg); chatInput.value = ''; }
        });
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
        });
    }

    // Load memory count
    updateMemoryCount();
}

// ─────────────────────────────────────────────
// File Upload
// ─────────────────────────────────────────────

function uploadFile(file) {
    const uploadContent = document.getElementById('upload-content');
    const uploadStatus = document.getElementById('upload-status');
    const uploadFilename = document.getElementById('upload-filename');
    const uploadChars = document.getElementById('upload-chars');

    uploadContent.innerHTML = `
        <div class="upload-icon" style="animation: pulse 1s infinite;">⏳</div>
        <p class="upload-text">Processing ${esc(file.name)}...</p>
    `;

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            resetUploadZone();
            if (data.error) {
                alert(data.error);
            } else {
                uploadStatus.style.display = 'block';
                uploadFilename.textContent = data.filename;
                uploadChars.textContent = `${data.char_count.toLocaleString()} chars`;
            }
        })
        .catch(err => {
            resetUploadZone();
            alert('Upload failed: ' + err.message);
        });
}

function resetUploadZone() {
    const uploadContent = document.getElementById('upload-content');
    uploadContent.innerHTML = `
        <div class="upload-icon">📁</div>
        <p class="upload-text">Drag & drop or click to upload</p>
        <p class="upload-hint">PDF or TXT • Max 16MB</p>
    `;
}

// ─────────────────────────────────────────────
// Run Analysis
// ─────────────────────────────────────────────

function runAnalysis(feature) {
    const contractText = document.getElementById('contract-text').value.trim();
    let extra_context = "";
    if (feature === "compare") {
        extra_context = prompt("Please paste the secondary contract text for comparison:");
        if (!extra_context) {
            document.querySelectorAll('.feature-btn').forEach(b => b.classList.remove('active'));
            return;
        }
    } else if (feature === "multilingual") {
        extra_context = prompt("What language do you want to translate to? (e.g., English, Spanish, French)", "English");
        if (!extra_context) {
            document.querySelectorAll('.feature-btn').forEach(b => b.classList.remove('active'));
            return;
        }
    }

    const resultsLoading = document.getElementById('results-loading');
    const resultsEmpty = document.getElementById('results-empty');
    const resultsContent = document.getElementById('results-content');
    const resultsError = document.getElementById('results-error');
    const resultsTitle = document.getElementById('results-title');
    const resultsBadge = document.getElementById('results-badge');
    const chatSection = document.getElementById('chat-section');

    // Show loading
    resultsLoading.style.display = 'flex';
    resultsEmpty.style.display = 'none';
    resultsContent.style.display = 'none';
    resultsError.style.display = 'none';
    chatSection.style.display = 'none';

    // Disable buttons
    document.querySelectorAll('.feature-btn').forEach(b => b.disabled = true);

    fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature, contract_text: contractText, extra_context }),
    })
    .then(r => r.json())
    .then(data => {
        resultsLoading.style.display = 'none';
        document.querySelectorAll('.feature-btn').forEach(b => b.disabled = false);

        if (data.result && data.result.error) {
            showError(data.result.error);
            return;
        }

        // Update header
        resultsTitle.textContent = `📊 ${data.feature_label}`;
        resultsBadge.textContent = data.feature;
        resultsBadge.style.display = 'inline-block';

        // Render results
        resultsContent.innerHTML = renderResults(data.feature, data.result);
        resultsContent.style.display = 'block';

        // Show chat section
        chatSection.style.display = 'block';

        // Update memory count
        updateMemoryCount();
    })
    .catch(err => {
        resultsLoading.style.display = 'none';
        document.querySelectorAll('.feature-btn').forEach(b => b.disabled = false);
        showError('Network error: ' + err.message);
    });
}

function showError(msg) {
    const resultsError = document.getElementById('results-error');
    const errorText = document.getElementById('error-text');
    resultsError.style.display = 'flex';
    errorText.textContent = msg;
}

// ─────────────────────────────────────────────
// Result Renderers
// ─────────────────────────────────────────────

function renderResults(feature, data) {
    switch (feature) {
        case 'summarize': return renderSummarize(data);
        case 'translate': return renderTranslate(data);
        case 'risks':     return renderRisks(data);
        case 'tags':      return renderTags(data);
        case 'entities':  return renderEntities(data);
        case 'compare':   return renderCompare(data);
        case 'multilingual': return renderMultilingual(data);
        default:          return `<pre>${JSON.stringify(data, null, 2)}</pre>`;
    }
}

function renderSummarize(d) {
    let html = renderSummaryCard(d.quick_summary);
    html += `<p style="color:var(--text-muted);font-size:0.85rem;margin-bottom:var(--space-lg);">Total clauses found: <strong style="color:var(--gold-primary)">${d.total_clauses || '—'}</strong></p>`;

    if (d.clauses) {
        d.clauses.forEach(c => {
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">${esc(c.title || 'Clause')}</span>
                    <span class="result-item-number">Clause ${c.clause_number}</span>
                </div>
                ${c.original_text_snippet ? `<div class="original-snippet">"${esc(c.original_text_snippet)}"</div>` : ''}
                <p class="plain-text-block">${esc(c.plain_summary || '')}</p>
                ${renderKeyPoints(c.key_points)}
            </div>`;
        });
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderTranslate(d) {
    let html = renderSummaryCard(d.quick_summary);
    html += `<p style="color:var(--text-muted);font-size:0.85rem;margin-bottom:var(--space-lg);">Overall complexity: <span class="severity severity-${(d.overall_complexity || 'medium').toLowerCase()}">${d.overall_complexity || '—'}</span></p>`;

    if (d.sections) {
        d.sections.forEach(s => {
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">${esc(s.original_heading || 'Section')}</span>
                    <span class="severity severity-${(s.complexity_rating || 'medium').toLowerCase()}">${s.complexity_rating || '—'}</span>
                </div>
                ${s.original_text_snippet ? `<div class="original-snippet">"${esc(s.original_text_snippet)}"</div>` : ''}
                <p class="plain-text-block">${esc(s.plain_language || '')}</p>
                ${s.why_it_matters ? `<p style="margin-top:var(--space-sm);font-size:0.85rem;color:var(--gold-primary);">💡 ${esc(s.why_it_matters)}</p>` : ''}
            </div>`;
        });
    }

    // Jargon glossary
    if (d.jargon_glossary && d.jargon_glossary.length > 0) {
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">📖 Jargon Glossary</h3>
            <table class="glossary-table">
                <thead><tr><th>Legal Term</th><th>Plain Meaning</th></tr></thead>
                <tbody>${d.jargon_glossary.map(g => `<tr><td><strong>${esc(g.term)}</strong></td><td>${esc(g.plain_meaning)}</td></tr>`).join('')}</tbody>
            </table>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderRisks(d) {
    let html = renderSummaryCard(d.quick_summary);

    // Risk breakdown
    const rb = d.risk_breakdown || {};
    html += `<div class="risk-breakdown">
        <div class="risk-stat"><span class="risk-dot risk-dot-high"></span> HIGH: <strong>${rb.HIGH || 0}</strong></div>
        <div class="risk-stat"><span class="risk-dot risk-dot-medium"></span> MEDIUM: <strong>${rb.MEDIUM || 0}</strong></div>
        <div class="risk-stat"><span class="risk-dot risk-dot-low"></span> LOW: <strong>${rb.LOW || 0}</strong></div>
        <span style="margin-left:auto;font-size:0.85rem;color:var(--text-muted);">Overall: <span class="severity severity-${(d.overall_risk_level || 'medium').toLowerCase()}">${d.overall_risk_level || '—'}</span></span>
    </div>`;

    if (d.risks) {
        d.risks.forEach(r => {
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">⚠️ ${esc(r.risk_type || 'Risk')}</span>
                    <span class="severity severity-${(r.severity || 'medium').toLowerCase()}">${r.severity || '—'}</span>
                </div>
                ${r.clause_text_snippet ? `<div class="original-snippet">"${esc(r.clause_text_snippet)}"</div>` : ''}
                <p class="plain-text-block">${esc(r.explanation || '')}</p>
                ${r.potential_impact ? `<p style="margin-top:var(--space-sm);font-size:0.88rem;color:var(--risk-medium);">⚡ Impact: ${esc(r.potential_impact)}</p>` : ''}
                ${r.negotiation_tip ? `<div class="negotiation-tip"><strong>💡 Negotiation tip:</strong> ${esc(r.negotiation_tip)}</div>` : ''}
            </div>`;
        });
    }

    if (d.safe_clauses_note) {
        html += `<div class="result-item" style="border-color:rgba(39,174,96,0.2);">
            <p style="color:var(--risk-low);">✅ ${esc(d.safe_clauses_note)}</p>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderTags(d) {
    let html = renderSummaryCard(d.quick_summary);

    // Category frequency
    if (d.category_frequency) {
        html += `<div class="frequency-grid">`;
        for (const [cat, count] of Object.entries(d.category_frequency)) {
            if (count > 0) {
                html += `<span class="freq-chip">${esc(cat)} <strong>${count}</strong></span>`;
            }
        }
        html += `</div>`;
    }

    if (d.tagged_clauses) {
        d.tagged_clauses.forEach(c => {
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="category-tag">${esc(c.primary_category || 'Other')}</span>
                    <span class="result-item-number">Clause ${c.clause_number}</span>
                    <span class="severity severity-${(c.confidence || 'medium').toLowerCase()}">${c.confidence || '—'}</span>
                </div>
                ${c.text_snippet ? `<div class="original-snippet">"${esc(c.text_snippet)}"</div>` : ''}
                ${c.brief_note ? `<p class="plain-text-block">${esc(c.brief_note)}</p>` : ''}
                ${c.secondary_tags && c.secondary_tags.length ? `<div style="margin-top:var(--space-sm);display:flex;gap:4px;flex-wrap:wrap;">${c.secondary_tags.map(t => `<span class="freq-chip">${esc(t)}</span>`).join('')}</div>` : ''}
            </div>`;
        });
    }

    // Missing categories
    if (d.missing_categories && d.missing_categories.length > 0) {
        html += `<div class="result-item" style="border-color:rgba(243,156,18,0.2);">
            <p style="color:var(--risk-medium);font-size:0.9rem;">⚠️ Missing categories commonly expected in contracts:</p>
            <div style="margin-top:var(--space-sm);display:flex;gap:4px;flex-wrap:wrap;">${d.missing_categories.map(c => `<span class="freq-chip">${esc(c)}</span>`).join('')}</div>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderEntities(d) {
    let html = renderSummaryCard(d.quick_summary);

    // Parties
    if (d.parties && d.parties.length > 0) {
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">🤝 Parties &amp; Obligations</h3>`;
        d.parties.forEach(p => {
            html += `<div style="margin-bottom:var(--space-md);padding:var(--space-sm);border-left:3px solid var(--gold-primary);">
                <p style="font-weight:600;color:var(--gold-primary);">${esc(p.role || 'Party')}: <span style="color:var(--text-primary);">${esc(p.name || '—')}</span></p>
                ${renderKeyPoints(p.key_obligations)}
            </div>`;
        });
        html += `</div>`;
    }

    // Important dates
    if (d.important_dates && d.important_dates.length > 0) {
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">📅 Key Dates</h3>
            <table class="glossary-table">
                <thead><tr><th>Label</th><th>Value</th><th>Note</th></tr></thead>
                <tbody>${d.important_dates.map(dt =>
                    `<tr><td><strong>${esc(dt.label)}</strong></td><td style="color:var(--gold-primary);">${esc(dt.value)}</td><td>${esc(dt.note)}</td></tr>`
                ).join('')}</tbody>
            </table>
        </div>`;
    }

    // Payment terms
    if (d.payment_terms) {
        const pt = d.payment_terms;
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">💰 Payment Terms</h3>
            <table class="glossary-table">
                <tbody>
                    <tr><td><strong>Amount</strong></td><td>${esc(pt.amount || '—')}</td></tr>
                    <tr><td><strong>Currency</strong></td><td>${esc(pt.currency || '—')}</td></tr>
                    <tr><td><strong>Schedule</strong></td><td>${esc(pt.schedule || '—')}</td></tr>
                    <tr><td><strong>Late Penalty</strong></td><td>${esc(pt.late_penalty || '—')}</td></tr>
                </tbody>
            </table>
        </div>`;
    }

    // Governing law
    if (d.governing_law) {
        const gl = d.governing_law;
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">⚖️ Governing Law</h3>
            <p><strong>Jurisdiction:</strong> ${esc(gl.jurisdiction || '—')}</p>
            <p><strong>Forum:</strong> ${esc(gl.court_or_arbitration || '—')}</p>
            ${gl.risk_note ? `<p style="margin-top:var(--space-sm);color:var(--risk-medium);font-size:0.88rem;">⚡ ${esc(gl.risk_note)}</p>` : ''}
        </div>`;
    }

    // Notice period
    if (d.notice_period && d.notice_period !== 'N/A') {
        html += `<div class="result-item">
            <p>📣 <strong>Notice Period:</strong> ${esc(d.notice_period)}</p>
        </div>`;
    }

    // Defined terms
    if (d.defined_terms && d.defined_terms.length > 0) {
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">📖 Defined Terms</h3>
            <table class="glossary-table">
                <thead><tr><th>Term</th><th>Definition</th></tr></thead>
                <tbody>${d.defined_terms.map(dt =>
                    `<tr><td><strong>${esc(dt.term)}</strong></td><td>${esc(dt.definition)}</td></tr>`
                ).join('')}</tbody>
            </table>
        </div>`;
    }

    // Missing entities warning
    if (d.missing_entities && d.missing_entities.length > 0) {
        html += `<div class="result-item" style="border-color:rgba(243,156,18,0.2);">
            <p style="color:var(--risk-medium);font-size:0.9rem;">⚠️ Fields not found in this contract:</p>
            <div style="margin-top:var(--space-sm);display:flex;gap:4px;flex-wrap:wrap;">${d.missing_entities.map(e => `<span class="freq-chip">${esc(e)}</span>`).join('')}</div>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderCompare(d) {
    let html = renderSummaryCard(d.quick_summary);

    // Verdict badge
    const verdictMap = {
        FAVORABLE_TO_A: { label: 'Favors Original (A)', cls: 'severity-low' },
        FAVORABLE_TO_B: { label: 'Favors Revision (B)', cls: 'severity-high' },
        NEUTRAL:        { label: 'Neutral', cls: 'severity-low' },
        MIXED:          { label: 'Mixed', cls: 'severity-medium' },
    };
    const verdict = verdictMap[d.overall_verdict] || { label: d.overall_verdict || '—', cls: 'severity-medium' };
    html += `<div style="margin-bottom:var(--space-lg);display:flex;align-items:center;gap:var(--space-md);flex-wrap:wrap;">
        <span>Overall Verdict: <span class="severity ${verdict.cls}">${verdict.label}</span></span>
        <span style="color:var(--text-muted);font-size:0.85rem;">Total changes: <strong style="color:var(--gold-primary);">${d.total_changes || 0}</strong></span>
    </div>`;

    // Changes
    if (d.changes && d.changes.length > 0) {
        d.changes.forEach(c => {
            const sevCls = `severity-${(c.impact_severity || 'medium').toLowerCase()}`;
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">🔀 ${esc(c.clause_or_section || 'Change')}</span>
                    <span class="severity ${sevCls}">${c.impact_severity || '—'}</span>
                    <span style="font-size:0.78rem;color:var(--text-muted);">${esc(c.change_type || '')}</span>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-sm);margin:var(--space-sm) 0;">
                    <div class="original-snippet" style="border-left-color:#e74c3c;">🅰 ${esc(c.original_text_snippet || '—')}</div>
                    <div class="original-snippet" style="border-left-color:#27ae60;">🅱 ${esc(c.revised_text_snippet || '—')}</div>
                </div>
                <p class="plain-text-block">${esc(c.plain_explanation || '')}</p>
                ${c.who_benefits ? `<p style="font-size:0.85rem;color:var(--text-muted);">👤 Benefits: <strong>${esc(c.who_benefits)}</strong></p>` : ''}
                ${c.negotiation_note ? `<div class="negotiation-tip"><strong>💡 Negotiation note:</strong> ${esc(c.negotiation_note)}</div>` : ''}
            </div>`;
        });
    }

    // Unchanged key clauses
    if (d.unchanged_key_clauses && d.unchanged_key_clauses.length > 0) {
        html += `<div class="result-item" style="border-color:rgba(39,174,96,0.2);">
            <p style="color:var(--risk-low);font-weight:600;margin-bottom:var(--space-sm);">✅ Key clauses unchanged:</p>
            <ul class="key-points">${d.unchanged_key_clauses.map(cl => `<li>${esc(cl)}</li>`).join('')}</ul>
        </div>`;
    }

    // Executive recommendation
    if (d.executive_recommendation) {
        html += `<div class="result-summary-card" style="margin-top:var(--space-lg);border-color:var(--gold-primary);">
            <h3>🎯 Executive Recommendation</h3>
            <p>${esc(d.executive_recommendation)}</p>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

function renderMultilingual(d) {
    let html = `<div class="result-summary-card">
        <h3>🌐 Translated to: <span style="color:var(--gold-primary);">${esc(d.target_language || '—')}</span></h3>
        <p>${esc(d.quick_summary || '')}</p>
    </div>`;

    if (d.sections && d.sections.length > 0) {
        d.sections.forEach(s => {
            html += `<div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">${esc(s.translated_heading || s.original_heading || 'Section')}</span>
                    <span class="result-item-number">§${s.section_number}</span>
                </div>
                <p class="plain-text-block">${esc(s.translated_text || '')}</p>
                ${s.key_obligation ? `<p style="margin-top:var(--space-sm);font-size:0.85rem;color:var(--gold-primary);">🔑 ${esc(s.key_obligation)}</p>` : ''}
            </div>`;
        });
    }

    // Critical terms glossary
    if (d.critical_terms_glossary && d.critical_terms_glossary.length > 0) {
        html += `<div class="result-item">
            <h3 class="result-item-title" style="margin-bottom:var(--space-md);">📖 Critical Terms Glossary</h3>
            <table class="glossary-table">
                <thead><tr><th>Original Term</th><th>Translated Term</th><th>Plain Meaning</th></tr></thead>
                <tbody>${d.critical_terms_glossary.map(g =>
                    `<tr><td><strong>${esc(g.original_term)}</strong></td><td style="color:var(--gold-primary);">${esc(g.translated_term)}</td><td>${esc(g.plain_explanation)}</td></tr>`
                ).join('')}</tbody>
            </table>
        </div>`;
    }

    // Translation notes
    if (d.translation_notes && d.translation_notes.length > 0) {
        html += `<div class="result-item" style="border-color:rgba(243,156,18,0.2);">
            <p style="color:var(--risk-medium);font-weight:600;margin-bottom:var(--space-sm);">📝 Translator Notes:</p>
            <ul class="key-points">${d.translation_notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
        </div>`;
    }

    html += renderRecommendations(d.recommendations);
    return html;
}

// ─────────────────────────────────────────────
// Shared render helpers
// ─────────────────────────────────────────────

function renderSummaryCard(summary) {
    if (!summary) return '';
    return `<div class="result-summary-card">
        <h3>📌 Quick Summary</h3>
        <p>${esc(summary)}</p>
    </div>`;
}

function renderKeyPoints(points) {
    if (!points || points.length === 0) return '';
    return `<ul class="key-points">${points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>`;
}

function renderRecommendations(recs) {
    if (!recs || recs.length === 0) return '';
    return `<div class="recommendations">
        <h3>💡 Recommendations</h3>
        <ul>${recs.map(r => `<li>${esc(r)}</li>`).join('')}</ul>
    </div>`;
}

// ─────────────────────────────────────────────
// Follow-up Chat
// ─────────────────────────────────────────────

function sendChat(message) {
    const chatMessages = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('send-btn');

    // Add user message
    appendChatMessage('user', message);
    sendBtn.disabled = true;

    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
    })
    .then(r => r.json())
    .then(data => {
        sendBtn.disabled = false;
        if (data.error) {
            appendChatMessage('assistant', `⚠️ ${data.error}`);
        } else {
            appendChatMessage('assistant', data.answer || 'No response.');

            // Show follow-up suggestions
            if (data.follow_up_suggestions && data.follow_up_suggestions.length > 0) {
                renderSuggestions(data.follow_up_suggestions);
            }
        }
        updateMemoryCount();
    })
    .catch(err => {
        sendBtn.disabled = false;
        appendChatMessage('assistant', `❌ Network error: ${err.message}`);
    });
}

function appendChatMessage(role, content) {
    const chatMessages = document.getElementById('chat-messages');
    const avatar = role === 'user' ? '👤' : '⚖️';
    const div = document.createElement('div');
    div.className = `message message-${role}`;
    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-bubble">${esc(content)}</div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderSuggestions(suggestions) {
    // Remove old suggestions
    const old = document.querySelector('.follow-up-suggestions');
    if (old) old.remove();

    const container = document.createElement('div');
    container.className = 'follow-up-suggestions';
    suggestions.forEach(s => {
        const chip = document.createElement('button');
        chip.className = 'suggestion-chip';
        chip.textContent = s;
        chip.onclick = () => {
            document.getElementById('chat-input').value = s;
            sendChat(s);
            document.getElementById('chat-input').value = '';
            container.remove();
        };
        container.appendChild(chip);
    });

    const chatSection = document.getElementById('chat-section');
    const chatInputContainer = chatSection.querySelector('.chat-input-container');
    chatSection.insertBefore(container, chatInputContainer);
}

// ─────────────────────────────────────────────
// Memory
// ─────────────────────────────────────────────

function updateMemoryCount() {
    fetch('/api/memory')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('memory-turns');
            if (el) el.textContent = data.turn_count || 0;
        })
        .catch(() => {});
}

function clearMemory() {
    if (!confirm('Clear all session memory?')) return;
    fetch('/api/clear-memory', { method: 'POST' })
        .then(r => r.json())
        .then(() => {
            updateMemoryCount();
            document.getElementById('upload-status').style.display = 'none';
            const chatMessages = document.getElementById('chat-messages');
            if (chatMessages) chatMessages.innerHTML = '';
        });
}

// ─────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────

function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}
