const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

let trendsChart = null;
let modulesChart = null;
let filterTimer = null;

async function getJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Błąd serwera (${response.status})`);
  return body;
}

// Szybkie próbki demonstracyjne
const SAMPLES = {
  m1: {
    author: "@finfluencer_lukasz",
    text: "Współpraca z XTB S.A.! Otwórz konto maklerskie z moim linkiem i kodem LUKASZ_VIP. Zysk gwarantowany z moją nową strategią daytradingową! Bez ryzyka i bez prowizji."
  },
  m2: {
    author: "Global Finance LTD",
    text: "Rewelacyjne zyski na kontraktach CFD! Nasza platforma jest pod stałym nadzorem KNF, co w 100% gwarantuje bezpieczeństwo twojego kapitału. Wyniki z przeszłości: +180% w 3 miesiące! Sprawdź ofertę na naszej stronie."
  },
  m3: {
    author: "Prestige Wealth Family Office",
    text: "Prestige Wealth Management oferuje kompleksowe doradztwo inwestycyjne i zarządzanie portfelem akcji spółek z GPW oraz obligacji skarbowych dla inwestorów zamożnych. Przygotowujemy indywidualne rekomendacje kupna i sprzedaży papierów wartościowych."
  },
  ok: {
    author: "Biuro Maklerskie PKO BP",
    text: "Biuro Maklerskie PKO Banku Polskiego informuje: Inwestowanie w instrumenty finansowe wiąże się z ryzykiem utraty części lub całości kapitału. Zapoznaj się z prospektem emisyjnym oraz tabelą opłat i prowizji."
  }
};

function initCharts() {
  const ctxTrends = $('#trendsChart');
  const ctxModules = $('#modulesChart');

  if (typeof Chart === 'undefined') {
    console.warn('Chart.js not loaded');
    return;
  }

  if (ctxTrends) {
    trendsChart = new Chart(ctxTrends, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Wszystkie incydenty',
            data: [],
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            tension: 0.3,
            fill: true
          },
          {
            label: 'Wysokie ryzyko (≥ 0.70)',
            data: [],
            borderColor: '#ff5263',
            backgroundColor: 'rgba(255, 82, 99, 0.1)',
            tension: 0.3,
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#8fa5be' } }
        },
        scales: {
          x: { ticks: { color: '#8fa5be' }, grid: { color: '#1e3550' } },
          y: { ticks: { color: '#8fa5be', stepSize: 1 }, grid: { color: '#1e3550' }, beginAtZero: true }
        }
      }
    });
  }

  if (ctxModules) {
    modulesChart = new Chart(ctxModules, {
      type: 'doughnut',
      data: {
        labels: ['M1: Finfluencerzy', 'M2: Ryzyko', 'M3: Shadow Adv.'],
        datasets: [{
          data: [0, 0, 0],
          backgroundColor: ['#38bdf8', '#fb923c', '#f43f5e'],
          borderColor: '#0d1b2a',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#8fa5be' } }
        }
      }
    });
  }
}

async function updateCharts() {
  try {
    const [trends, summary] = await Promise.all([
      fetch('/api/analytics/trends').then(r => r.json()),
      fetch('/api/analytics/summary?threshold=' + $('#threshold').value).then(r => r.json())
    ]);

    if (trendsChart && trends.length) {
      trendsChart.data.labels = trends.map(t => t.date);
      trendsChart.data.datasets[0].data = trends.map(t => t.total);
      trendsChart.data.datasets[1].data = trends.map(t => t.high);
      trendsChart.update();
    }

    if (modulesChart && summary.by_module) {
      modulesChart.data.datasets[0].data = [
        summary.by_module.m1 || 0,
        summary.by_module.m2 || 0,
        summary.by_module.m3 || 0
      ];
      modulesChart.update();
    }
  } catch (err) {
    console.error('Error updating charts:', err);
  }
}

async function loadData() {
  const thresholdVal = parseFloat($('#threshold').value);
  $('#thresholdDisplay').textContent = thresholdVal.toFixed(2);

  const params = new URLSearchParams({ min_risk: thresholdVal });
  if ($('#sourceFilter').value) params.set('source', $('#sourceFilter').value);
  if ($('#moduleFilter').value) params.set('module', $('#moduleFilter').value);

  try {
    const [findings, summary] = await Promise.all([
      getJson('/api/findings?' + params),
      getJson('/api/analytics/summary?threshold=' + thresholdVal)
    ]);

    // Uaktualnienie wskaźników statystycznych
    $('#statTotal').textContent = summary.total;
    $('#statHigh').textContent = summary.high_risk;
    $('#statReview').textContent = summary.new;
    const reviewed = summary.reviewed_metrics || {};
    $('#statFp').textContent = reviewed.false_positive ?? 0;
    $('#statFn').textContent = reviewed.false_negative ?? 0;
    $('#statPrecision').textContent = reviewed.precision == null ? '—' : reviewed.precision + '%';
    $('#statRecall').textContent = reviewed.recall == null ? '—' : reviewed.recall + '%';
    $('#reviewedSampleCount').textContent = `Metryki liczą ${reviewed.reviewed_count || 0} ręcznie ocenionych wyników. Zmień status wyniku, aby dodać ocenę.`;

    // Renderowanie wierszy tabeli
    const rows = $('#findingsRows');
    if (!findings.length) {
      rows.innerHTML = '<div class="empty-state"><b>Brak wyników dla tych filtrów</b><span>Obniż próg ryzyka albo zmień wyszukiwaną domenę lub moduł.</span></div>';
      updateCharts();
      return;
    }

    rows.innerHTML = findings.map(item => {
      let scoreClass = 'score-low';
      let riskLabel = 'Niskie';
      if (item.risk_score >= 0.70) { scoreClass = 'score-high'; riskLabel = 'Wysokie'; }
      else if (item.risk_score >= 0.40) { scoreClass = 'score-medium'; riskLabel = 'Umiarkowane'; }

      const modules = item.modules || [];
      const moduleNames = { 1: 'Finfluencerzy', 2: 'Informacja o ryzyku', 3: 'Shadow Advisory' };
      const moduleBadges = modules.length
        ? modules.map(m => `<span class="badge badge-m${m}">M${m} · ${moduleNames[m] || 'Moduł'}</span>`).join('')
        : '<span class="badge badge-neutral">Brak modułu</span>';

      const issues = item.audit?.issues || [];
      const modelReview = item.audit?.model_review;
      const modelVerdict = { supports: 'wspiera przesłankę', contradicts: 'wskazuje inny kontekst', uncertain: 'nie rozstrzyga' };
      const auditDetails = item.audit
        ? `<details class="audit-details">
             <summary>Przesłanki tekstowe: ${issues.length} · kontrola modelu: ${modelReview?.available ? esc(modelReview.model) : 'niedostępna'}</summary>
             ${issues.map(i => `
               <div class="issue-item">
                 <b>R${esc(i.id)}: ${esc(i.title)}</b> — ${esc(i.detail)}
                 <div class="issue-legal">Podstawa: ${esc(i.legal_basis)}</div>
                 ${i.evidence?.quote ? `<blockquote class="evidence-quote">„${esc(i.evidence.quote)}”<small>Fragment, na który trafiła reguła${i.evidence.matched_terms?.length ? ': ' + esc(i.evidence.matched_terms.join(', ')) : ''}</small></blockquote>` : ''}
                 ${modelReview?.available && modelReview.rule_reviews?.some(r => r.id === String(i.id)) ? modelReview.rule_reviews.filter(r => r.id === String(i.id)).map(r => `<div class="model-review">Model pomocniczo: <b>${esc(modelVerdict[r.verdict] || r.verdict)}</b>${r.quote_verified && r.quote ? ` · cytat: „${esc(r.quote)}”` : ''}</div>`).join('') : ''}
               </div>
             `).join('')}
             ${modelReview?.available ? `<div class="model-summary"><b>Podsumowanie kontekstu (${esc(modelReview.model)})</b><p>${esc(modelReview.summary || 'Model nie zwrócił podsumowania.')}</p>${modelReview.additional_signals?.length ? `<div class="model-signals"><b>Dodatkowe fragmenty do sprawdzenia</b>${modelReview.additional_signals.map(s => `<div><span>${esc(s.label)}</span><blockquote>„${esc(s.quote)}”</blockquote></div>`).join('')}</div>` : ''}<small>Model pomaga sprawdzić kontekst cytatów. Nie ustala wyniku ryzyka ani nie tworzy naruszeń.</small></div>` : `<div class="model-summary"><b>Model lokalny</b><p>${esc(modelReview?.error || 'Brak odpowiedzi Ollamy dla tej analizy.')}</p><small>Wynik ryzyka wyliczono z reguł i sygnałów deterministycznych.</small></div>`}
             ${item.audit.limitations?.length ? `<div class="audit-limitations">Zakres tej analizy: ${item.audit.limitations.map(esc).join(' ')}</div>` : ''}
           </details>`
        : '';

      const snapshotBtn = `<a class="result-link" href="/api/findings/${item.id}/snapshot" target="_blank" rel="noreferrer">Podgląd zrzutu ↗</a>`;
      const sourceUrl = esc(item.url);
      const created = item.created_at ? new Date(item.created_at).toLocaleString('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }) : '';
      const excerpt = item.text ? esc(item.text.slice(0, 260)) + (item.text.length > 260 ? '…' : '') : '';

      return `
        <article class="result-card">
          <div class="risk-column"><span class="risk-score ${scoreClass}">${item.risk_score.toFixed(2)}</span><span class="risk-label">${riskLabel} ryzyko</span></div>
          <div class="result-main">
            <div class="result-meta"><a class="source-name" href="${sourceUrl}" target="_blank" rel="noreferrer">${esc(item.source)} ↗</a>${item.author ? `<span class="author">${esc(item.author)}</span>` : ''}${created ? `<time>${esc(created)}</time>` : ''}</div>
            <div class="module-list">${moduleBadges}</div>
            <p class="result-reason">${esc(item.reason)}</p>
            ${excerpt ? `<details class="content-preview"><summary>Treść materiału</summary><p>${excerpt}</p></details>` : ''}
            ${auditDetails}
          </div>
          <div class="result-actions">${snapshotBtn}<label class="status-control"><span>Status</span><select data-id="${item.id}">${[['new','Do weryfikacji'],['reviewing','W trakcie'],['confirmed','Potwierdzone'],['dismissed','Odrzucone']].map(([value,label]) => `<option value="${value}" ${value === item.status ? 'selected' : ''}>${label}</option>`).join('')}</select></label></div>
        </article>
      `;
    }).join('');

    updateCharts();
    $('#scanStatusBox').textContent = '';
  } catch (err) {
    console.error('Error loading data:', err);
    $('#findingsRows').innerHTML = `<div class="empty-state error-state"><b>Nie udało się pobrać wyników</b><span>${esc(err.message)}. Sprawdź połączenie z backendem i spróbuj ponownie.</span></div>`;
    $('#scanStatusBox').textContent = 'Nie udało się odświeżyć dashboardu: ' + err.message;
  }
}

async function updateCrawlerStatus() {
  try {
    const status = await getJson('/api/crawler/status');
    $('#pagesAnalyzed').textContent = status.completed_scans;
    $('#findingsSaved').textContent = status.analyzed_pages;
    $('#findingsSavedDetail').textContent = status.analyzed_pages;
    $('#pagesQueued').textContent = status.queued_scans;
    $('#pagesFailed').textContent = status.failed_scans;
    $('#pagesFailedDetail').textContent = status.failed_scans;
    const failures = status.recent_failures || [];
    $('#crawlerFailures').innerHTML = failures.length
      ? '<b>Ostatnie błędy skanowania</b>' + failures.map(f => `<div class="crawler-failure"><a href="${esc(f.url)}" target="_blank" rel="noreferrer">${esc(f.url)}</a><span>${esc(f.error || 'Brak opisu błędu')}</span></div>`).join('')
      : '<span class="no-failures">Brak ostatnich błędów. Skaner działa poprawnie.</span>';
    if (status.is_working) {
      const stage = status.current.stage === 'fetching_page' ? 'Pobieram stronę' : 'Analizuję treść';
      $('#crawlerState').textContent = '● ' + stage + '…';
      $('#crawlerState').style.color = 'var(--accent)';
      const elapsed = status.current.started_at ? Math.max(0, Math.floor(Date.now() / 1000 - new Date(status.current.started_at).getTime() / 1000)) : 0;
      $('#currentPage').innerHTML = 'Teraz (' + elapsed + ' s): <a target="_blank" rel="noreferrer" href="' + esc(status.current.url) + '">' + esc(status.current.url) + '</a>';
    } else if (status.discovery.stage === 'searching') {
      $('#crawlerState').textContent = '● Szukam nowych publicznych stron…';
      $('#crawlerState').style.color = 'var(--accent)';
      $('#currentPage').textContent = 'Przeszukuję Google News RSS po ' + (status.watchlist_count || 20) + ' hasłach.';
    } else {
      const secondsLeft = Math.max(0, Math.ceil(status.discovery.next_run_at - Date.now() / 1000));
      const minutes = Math.floor(secondsLeft / 60);
      const seconds = secondsLeft % 60;
      $('#crawlerState').textContent = '● Skaner działa — kolejne wyszukiwanie za ' + (minutes ? minutes + ' min ' : '') + seconds + ' s';
      $('#crawlerState').style.color = 'var(--muted)';
      if (status.discovery.last_error) {
        $('#currentPage').textContent = 'Ostatnie wyszukiwanie nie powiodło się: ' + status.discovery.last_error;
      } else {
        const lastRun = status.discovery.last_finished_at ? new Date(status.discovery.last_finished_at).toLocaleTimeString('pl-PL') : 'jeszcze się nie odbyło';
        $('#currentPage').textContent = 'Ostatnie wyszukiwanie: ' + lastRun + ' · wpisy RSS: ' + (status.discovery.feed_items ?? '—') + ' · pasujące finansowo: ' + (status.discovery.relevant_items ?? '—') + ' · nowe adresy w kolejce: ' + status.discovery.last_found + '. Wyszukiwanie uruchamia się automatycznie.';
      }
    }
  } catch (err) {
    $('#crawlerState').textContent = 'Nie można pobrać statusu skanera';
    $('#currentPage').textContent = 'Sprawdź połączenie z backendem.';
  }
}

// Zmiana statusu incydentu
$('#findingsRows').addEventListener('change', async e => {
  if (e.target.dataset.id) {
    const select = e.target;
    select.disabled = true;
    try {
    await getJson(`/api/findings/${select.dataset.id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: select.value })
    });
    loadData();
    } catch (err) {
      $('#scanStatusBox').textContent = 'Nie udało się zapisać statusu: ' + err.message;
      select.disabled = false;
    }
  }
});

// Zmiana progu detekcji i filtrów
$('#threshold').addEventListener('input', () => {
  $('#thresholdDisplay').textContent = parseFloat($('#threshold').value).toFixed(2);
  clearTimeout(filterTimer);
  filterTimer = setTimeout(loadData, 180);
});
$('#sourceFilter').addEventListener('input', () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(loadData, 250);
});
$('#moduleFilter').addEventListener('change', loadData);
$('#refreshBtn').addEventListener('click', () => { loadData(); updateCrawlerStatus(); });

$('#discoverBtn').addEventListener('click', async () => {
  const button = $('#discoverBtn');
  const status = $('#scanStatusBox');
  button.disabled = true;
  status.textContent = 'Szukam publicznych stron pasujących do monitorowanych haseł…';
  try {
    const result = await getJson('/api/discover', { method: 'POST' });
    status.textContent = `Google News RSS zwrócił ${result.feed_items} wpisów; ${result.relevant_items} pasuje do tematyki finansowej, ${result.queued} nowych adresów dodano do kolejki.`;
    updateCrawlerStatus();
    if (result.queued) setTimeout(() => { loadData(); updateCrawlerStatus(); }, 1500);
  } catch (err) {
    status.textContent = 'Błąd wyszukiwania: ' + err.message;
  } finally {
    button.disabled = false;
  }
});

// Obsługa zakładek skanowania
$('#tabUrlBtn').addEventListener('click', () => {
  $('#tabUrlBtn').classList.add('active');
  $('#tabTextBtn').classList.remove('active');
  $('#tabUrlContent').style.display = 'block';
  $('#tabTextContent').style.display = 'none';
});

$('#tabTextBtn').addEventListener('click', () => {
  $('#tabTextBtn').classList.add('active');
  $('#tabUrlBtn').classList.remove('active');
  $('#tabTextContent').style.display = 'block';
  $('#tabUrlContent').style.display = 'none';
});

// Skanowanie adresu URL
$('#urlScanForm').addEventListener('submit', async e => {
  e.preventDefault();
  const statusBox = $('#scanStatusBox');
  statusBox.textContent = 'Dodano zadanie do kolejki pobierania i analizy...';

  try {
    const job = await getJson('/api/scans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: $('#scanUrl').value,
        author: $('#scanAuthor').value || null
      })
    });
    statusBox.textContent = `Zadanie skanowania #${job.id} w toku. Oczekiwanie na wynik...`;

    const poll = setInterval(async () => {
      let jobCheck;
      try { jobCheck = await getJson('/api/jobs/' + job.id); } catch (err) {
        clearInterval(poll);
        statusBox.textContent = 'Nie udało się sprawdzić zadania: ' + err.message;
        return;
      }
      if (jobCheck.status === 'completed') {
        clearInterval(poll);
        statusBox.textContent = '✅ Skanowanie i analiza AI zakończone sukcesem.';
        loadData(); updateCrawlerStatus();
      } else if (jobCheck.status === 'failed') {
        clearInterval(poll);
        statusBox.textContent = '❌ Błąd podczas skanowania: ' + jobCheck.error;
      }
    }, 1000);
  } catch (err) {
    statusBox.textContent = '❌ Błąd: ' + err.message;
  }
});

// Bezpośrednia analiza tekstu
$('#directScanBtn').addEventListener('click', async () => {
  const text = $('#directText').value.trim();
  const author = $('#directAuthor').value.trim() || null;
  const statusBox = $('#scanStatusBox');

  if (!text) {
    statusBox.textContent = '⚠️ Wpisz tekst do analizy.';
    return;
  }

  statusBox.textContent = 'Analizuję tekst i sprawdzam sygnały ryzyka...';

  try {
    const result = await getJson('/api/scans/direct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, author })
    });
    statusBox.textContent = `✅ Analiza ukończona. Wykryte moduły: [${result.modules.map(m=>'M'+m).join(', ')}], Wskaźnik ryzyka: ${result.risk_score.toFixed(2)}`;
    loadData();
  } catch (err) {
    statusBox.textContent = '❌ Błąd analizy: ' + err.message;
  }
});

// Obsługa przycisków próbek demonstracyjnych
function setSample(sampleKey) {
  const sample = SAMPLES[sampleKey];
  if (!sample) return;
  $('#directAuthor').value = sample.author;
  $('#directText').value = sample.text;
  $('#scanStatusBox').textContent = 'Próbka jest gotowa. Możesz ją zmienić albo kliknąć „Analizuj tekst”.';
}

$('#sampleM1').addEventListener('click', () => setSample('m1'));
$('#sampleM2').addEventListener('click', () => setSample('m2'));
$('#sampleM3').addEventListener('click', () => setSample('m3'));
$('#sampleOk').addEventListener('click', () => setSample('ok'));

// Połączenie WebSocket dla alertów czasu rzeczywistego
function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${location.host}/ws/alerts`);

  ws.onopen = () => {
    $('#connStatus').textContent = 'System online';
    $('#connStatus').classList.remove('offline');
  };

  ws.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'high_risk_finding') {
        const item = msg.finding;
        const alertBox = $('#liveAlertBox');
        alertBox.innerHTML = `⚠️ <b>ALERT CZASU RZECZYWISTEGO:</b> Wykryto incydent wysokiego ryzyka (risk_score: ${item.risk_score.toFixed(2)}) w źródle <u>${esc(item.source)}</u>! Moduły: [${item.modules.map(m=>'M'+m).join(', ')}]`;
        alertBox.style.display = 'block';
        setTimeout(() => { alertBox.style.display = 'none'; }, 9000);
        loadData();
      }
    } catch (err) {
      console.error('Error handling WebSocket message:', err);
    }
  };

  ws.onclose = () => {
    $('#connStatus').textContent = 'Ponawiam połączenie…';
    $('#connStatus').classList.add('offline');
    setTimeout(connectWebSocket, 3000);
  };
}

// Inicjalizacja przy załadowaniu strony
window.addEventListener('DOMContentLoaded', () => {
  initCharts();
  loadData();
  updateCrawlerStatus();
  setInterval(updateCrawlerStatus, 4000);
  setInterval(loadData, 15000);
  connectWebSocket();
});
