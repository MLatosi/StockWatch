const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

let trendsChart = null;
let modulesChart = null;

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
      fetch('/api/findings?' + params).then(r => r.json()),
      fetch('/api/analytics/summary?threshold=' + thresholdVal).then(r => r.json())
    ]);

    // Uaktualnienie wskaźników statystycznych
    $('#statTotal').textContent = summary.total;
    $('#statHigh').textContent = summary.high_risk;
    $('#statReview').textContent = summary.new;
    $('#statFp').textContent = summary.estimated_false_positive;
    $('#statFn').textContent = summary.estimated_false_negative;

    // Renderowanie wierszy tabeli
    const rows = $('#findingsRows');
    if (!findings.length) {
      rows.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--muted); padding: 24px;">Brak rekordów spełniających wybrane kryteria i próg ryzyka.</td></tr>';
      return;
    }

    rows.innerHTML = findings.map(item => {
      let scoreClass = 'score-low';
      if (item.risk_score >= 0.70) scoreClass = 'score-high';
      else if (item.risk_score >= 0.40) scoreClass = 'score-medium';

      const moduleBadges = item.modules.length
        ? item.modules.map(m => `<span class="badge badge-m${m}">M${m}</span>`).join(' ')
        : '<span style="color: var(--muted);">—</span>';

      const auditDetails = item.audit && item.audit.issues && item.audit.issues.length
        ? `<details>
             <summary>Audyt 18 reguł KNF: ${item.audit.issues.length} naruszeń</summary>
             ${item.audit.issues.map(i => `
               <div class="issue-item">
                 <b>R${esc(i.id)}: ${esc(i.title)}</b> — ${esc(i.detail)}
                 <div class="issue-legal">Podstawa: ${esc(i.legal_basis)}</div>
               </div>
             `).join('')}
           </details>`
        : '';

      const snapshotBtn = `<a href="/api/findings/${item.id}/snapshot" target="_blank" style="color: var(--accent); text-decoration: none; font-size: 13px;">👁️ Podgląd</a>`;

      return `
        <tr>
          <td><span class="score-badge ${scoreClass}">${item.risk_score.toFixed(2)}</span></td>
          <td>${moduleBadges}</td>
          <td>
            <a href="${esc(item.url)}" target="_blank" rel="noreferrer" style="color: var(--accent); text-decoration: none; font-weight: 600;">${esc(item.source)}</a>
            ${item.author ? `<div style="font-size: 12px; color: var(--muted);">👤 ${esc(item.author)}</div>` : ''}
          </td>
          <td>
            <div>${esc(item.reason)}</div>
            ${auditDetails}
          </td>
          <td>${snapshotBtn}</td>
          <td>
            <select data-id="${item.id}" style="padding: 4px 8px; font-size: 13px;">
              ${['new', 'reviewing', 'confirmed', 'dismissed'].map(s => `
                <option value="${s}" ${s === item.status ? 'selected' : ''}>${s}</option>
              `).join('')}
            </select>
          </td>
        </tr>
      `;
    }).join('');

    updateCharts();
  } catch (err) {
    console.error('Error loading data:', err);
  }
}

// Zmiana statusu incydentu
$('#findingsRows').addEventListener('change', async e => {
  if (e.target.dataset.id) {
    await fetch(`/api/findings/${e.target.dataset.id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: e.target.value })
    });
    loadData();
  }
});

// Zmiana progu detekcji i filtrów
$('#threshold').addEventListener('input', () => {
  $('#thresholdDisplay').textContent = parseFloat($('#threshold').value).toFixed(2);
  loadData();
});
$('#sourceFilter').addEventListener('input', loadData);
$('#moduleFilter').addEventListener('change', loadData);
$('#refreshBtn').addEventListener('click', loadData);

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
    const res = await fetch('/api/scans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: $('#scanUrl').value,
        author: $('#scanAuthor').value || null
      })
    });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || 'Błąd żądania');

    statusBox.textContent = `Zadanie skanowania #${job.id} w toku. Oczekiwanie na wynik...`;

    const poll = setInterval(async () => {
      const jobCheck = await fetch('/api/jobs/' + job.id).then(r => r.json());
      if (jobCheck.status === 'completed') {
        clearInterval(poll);
        statusBox.textContent = '✅ Skanowanie i analiza AI zakończone sukcesem.';
        loadData();
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

  statusBox.textContent = 'Analiza tekstu przez silnik AI (audyt 18 reguł)...';

  try {
    const res = await fetch('/api/scans/direct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, author })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Błąd analizy');

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
  $('#scanStatusBox').textContent = `Załadowano gotową próbkę. Kliknij 'Analizuj treść natychmiast' lub edytuj tekst.`;
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
    $('#connStatus').textContent = '● System Online';
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
    $('#connStatus').textContent = '● Rozłączono (reconnecting...)';
    $('#connStatus').classList.add('offline');
    setTimeout(connectWebSocket, 3000);
  };
}

// Inicjalizacja przy załadowaniu strony
window.addEventListener('DOMContentLoaded', () => {
  initCharts();
  loadData();
  connectWebSocket();
});
