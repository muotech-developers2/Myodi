const form = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const resultsFileInput = document.getElementById('results-file-input');
const loading = document.getElementById('loading');
const resultsSection = document.getElementById('results-section');
const resultsBody = document.getElementById('results-body');
const clearBtn = document.getElementById('clear-btn');
const recalcBtn = document.getElementById('recalculate-btn');
const downloadPdfBtn = document.getElementById('download-pdf-btn');

let currentRows = [];

function formatOdds(value) {
    if (value === null || value === undefined || value === '') return '—';
    return Number(value).toFixed(2);
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function renderRows(rows) {
    currentRows = rows;
    resultsBody.innerHTML = '';

    rows.forEach((row, index) => {
        const tr = document.createElement('tr');
        tr.className = row.confidence === 'low' ? 'confidence-low' : row.confidence === 'medium' ? 'confidence-medium' : '';

        tr.innerHTML = `
            <td>
                <div class="fw-semibold">${escapeHtml(row.home_team || 'Unknown')} vs ${escapeHtml(row.away_team || 'Unknown')}</div>
            </td>
            <td><input class="form-control form-control-sm" data-field="home_odds" data-index="${index}" value="${row.home_odds ?? ''}"></td>
            <td><input class="form-control form-control-sm" data-field="draw_odds" data-index="${index}" value="${row.draw_odds ?? ''}"></td>
            <td><input class="form-control form-control-sm" data-field="away_odds" data-index="${index}" value="${row.away_odds ?? ''}"></td>
            <td><input class="form-control form-control-sm" data-field="btts_yes" data-index="${index}" value="${row.btts_yes ?? ''}"></td>
            <td><input class="form-control form-control-sm" data-field="btts_no" data-index="${index}" value="${row.btts_no ?? ''}"></td>
            <td class="total-cell">${row.total !== null && row.total !== undefined ? Number(row.total).toFixed(2) : '—'}</td>
            <td class="result-score-cell">${escapeHtml(row.result_score || '—')}</td>
        `;
        resultsBody.appendChild(tr);
    });

    resultsSection.classList.remove('d-none');
}

function setLoadingState(isLoading) {
    loading.classList.toggle('d-none', !isLoading);
    const button = document.getElementById('analyze-btn');
    if (button) {
        button.disabled = isLoading;
        button.textContent = isLoading ? 'Analyzing...' : 'Analyze Image';
    }
}

form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
        alert('Please select a screenshot first.');
        return;
    }

    setLoadingState(true);
    const formData = new FormData();
    formData.append('file', file);
    if (resultsFileInput.files[0]) {
        formData.append('results_file', resultsFileInput.files[0]);
    }

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed.');
        }

        if (!data.matches || data.matches.length === 0) {
            resultsSection.classList.add('d-none');
            alert('No match rows were detected in the uploaded image.');
            return;
        }

        renderRows(data.matches);
    } catch (error) {
        alert(error.message || 'Something went wrong.');
    } finally {
        setLoadingState(false);
    }
});

clearBtn.addEventListener('click', function () {
    currentRows = [];
    resultsBody.innerHTML = '';
    resultsSection.classList.add('d-none');
    fileInput.value = '';
    resultsFileInput.value = '';
});

recalcBtn.addEventListener('click', async function () {
    if (!currentRows.length) return;

    const rows = currentRows.map((row, index) => {
        const rowInputs = document.querySelectorAll('[data-index="' + index + '"]');
        const values = {};
        rowInputs.forEach(input => {
            values[input.dataset.field] = input.value;
        });
        return {
            home_team: row.home_team,
            away_team: row.away_team,
            home_odds: values.home_odds,
            draw_odds: values.draw_odds,
            away_odds: values.away_odds,
            btts_yes: values.btts_yes,
            btts_no: values.btts_no,
            result_score: row.result_score,
        };
    });

    const response = await fetch('/api/recalculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
    });

    const data = await response.json();
    if (response.ok) {
        renderRows(data.rows.map((row, index) => ({
            id: index + 1,
            home_team: row.home_team,
            away_team: row.away_team,
            home_odds: Number(row.home_odds),
            draw_odds: Number(row.draw_odds),
            away_odds: Number(row.away_odds),
            btts_yes: Number(row.btts_yes),
            btts_no: Number(row.btts_no),
            total: Number(row.total),
            result_score: row.result_score,
            confidence: 'medium'
        })));
    }
});

downloadPdfBtn.addEventListener('click', function () {
    if (!currentRows.length) return;

    const rows = currentRows.map(row => [
        `${row.home_team} vs ${row.away_team}`,
        row.home_odds,
        row.draw_odds,
        row.away_odds,
        row.btts_yes,
        row.btts_no,
        row.total,
        row.result_score,
    ]);

    const { jsPDF } = window.jspdf;
    const document = new jsPDF({ orientation: 'landscape' });
    document.setFontSize(16);
    document.text('Virtual Game Odds Results', 14, 15);
    document.autoTable({
        startY: 22,
        head: [['Match', '1', 'X', '2', 'YES', 'NO', 'Total', 'Result']],
        body: rows,
        styles: { fontSize: 9, cellPadding: 3 },
        headStyles: { fillColor: [25, 135, 84] },
    });
    document.save('virtual_odds_results.pdf');
});
