// Dedicated JavaScript for Modul 3: Penempatan Antar Bank & Nostro Devisa
let chartInstInstance = null;
let chartCounterpartyInstance = null;
let currentRecords = [];
let currentHeaders = [];
let currentJournalEntries = [];
let dealsPageSize = 10;
let dealsCurrentPage = 1;
let journalPageSize = 5;
let journalCurrentPage = 1;
let doughnutSlices = [];
let doughnutHoverIdx = -1;
let chart2FilterMode = '10'; // Default Top 10
let rawChart2Data = {};
let rawChart2Title = '';
let rawChart2Tag = '';

// Helper Format Currency (IDR)
function formatRupiah(amount) {
    if (typeof amount !== 'number') return amount;
    return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

// Check Database & Fetch Bank Name
async function checkSystemStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        

        const alertBanner = document.getElementById('dbAlertBanner');
        const alertMsg = document.getElementById('dbAlertMessage');

        if (data.database && data.database.connected) {
            if (alertBanner) alertBanner.style.display = 'none';
        } else {
            if (alertBanner) {
                alertBanner.style.display = 'flex';
                alertMsg.textContent = `Koneksi ke database ${data.database.host} (${data.database.name}) belum terhubung. Menampilkan data riil (0 transaksi). Silakan pastikan jaringan/VPN Anda aktif.`;
            }
        }
    } catch (e) {
        console.warn('Gagal cek status sistem:', e);
    }
}

// Run Engine for Module 3 (Interbank)

// Fetch data tanpa kalkulasi ulang pipeline
async function fetchAndRenderData(cutOff) {
    const btn = document.getElementById('btnRunEngine');
    const btnText = document.getElementById('btnText');
    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = 'Memuat Data...';

    try {
        const response = await fetch(`/api/interbank/data?cut_off=${encodeURIComponent(cutOff)}`);
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                updateDashboard(data);
            }
        } else {
            console.error('Gagal mengambil data cut-off:', response.statusText);
        }
    } catch (err) {
        console.error('Koneksi server gagal:', err);
    } finally {
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = 'Jalankan Kalkulasi';
    }
}

async function runEngine() {
    const btn = document.getElementById('btnRunEngine');
    const btnText = document.getElementById('btnText');
    const cutOff = document.getElementById('cutOffDate').value;

    btn.disabled = true;
    btnText.textContent = 'Mengeksekusi...';

    try {
        const response = await fetch('/api/run-engine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cut_off: cutOff,
                module: 'interbank'
            })
        });

        const data = await response.json();
        if (data.success) {
            updateDashboard(data);
        } else {
            alert('Gagal mengeksekusi engine: ' + (data.message || data.error));
        }
    } catch (err) {
        console.error('Koneksi server gagal:', err);
    } finally {
        btn.disabled = false;
        btnText.textContent = 'Jalankan Kalkulasi';
    }
}

// Render Badge Warna & Rincian di Bawah Chart (Poin 2)
function renderChart1Legend(labels, values, colors, chartTitle) {
    const legendBox = document.getElementById('chart1Legend');
    if (!legendBox) return;
    const total = values.reduce((a, b) => a + Number(b || 0), 0);
    const titleStr = String(chartTitle || '').toLowerCase();
    const isMoney = titleStr.includes('ead') || titleStr.includes('portofolio') || titleStr.includes('eksposur') || titleStr.includes('ckpn') || total > 1000000;

    legendBox.style.display = 'flex';
    legendBox.innerHTML = labels.map((lbl, idx) => {
        const val = Number(values[idx] || 0);
        const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0.0';
        const color = colors[idx % colors.length];
        let valFormatted;
        if (isMoney) {
            if (val >= 1000000000) {
                valFormatted = 'Rp ' + (val / 1000000000).toFixed(2) + ' M';
            } else if (val >= 1000000) {
                valFormatted = 'Rp ' + (val / 1000000).toFixed(1) + ' Jt';
            } else {
                valFormatted = 'Rp ' + val.toLocaleString('id-ID');
            }
        } else {
            valFormatted = val.toLocaleString('id-ID') + ' Mitra';
        }
        return `
            <div class="legend-chip">
                <span class="legend-color-dot" style="background-color: ${color};"></span>
                <span class="legend-chip-title">${lbl}:</span>
                <span class="legend-chip-val">${valFormatted} (${pct}%)</span>
            </div>
        `;
    }).join('');
}

// Update DOM with Engine Output
function updateDashboard(data) {
    const summary = data.summary;
    const tableData = data.table || {};
    currentRecords = tableData.records || [];
    currentHeaders = tableData.headers || [];
    currentJournalEntries = data.journal || [];
    dealsCurrentPage = 1;
    journalCurrentPage = 1;


    // 2. Update KPI Labels and Values
    document.getElementById('kpi1Title').textContent = summary.kpi1_title;
    document.getElementById('kpi1Sub').textContent = summary.kpi1_sub;
    document.getElementById('kpiTotalEad').textContent = typeof summary.kpi1_val === 'number' ? formatRupiah(summary.kpi1_val) : summary.kpi1_val;

    document.getElementById('kpi2Title').textContent = summary.kpi2_title;
    document.getElementById('kpiTotalCkpn').textContent = typeof summary.kpi2_val === 'number' ? formatRupiah(summary.kpi2_val) : summary.kpi2_val;
    document.getElementById('kpiCoverage').textContent = summary.kpi2_sub;

    document.getElementById('kpi3Title').textContent = summary.kpi3_title;
    document.getElementById('kpiStage1').textContent = summary.kpi3_s1;
    document.getElementById('kpiStage2').textContent = summary.kpi3_s2;
    document.getElementById('kpi3Desc1').textContent = summary.kpi3_desc1;
    document.getElementById('kpi3Desc2').textContent = summary.kpi3_desc2;

    document.getElementById('kpi4Title').textContent = summary.kpi4_title;
    document.getElementById('kpiAvgPd').textContent = summary.kpi4_val;
    document.getElementById('kpi4Sub').textContent = summary.kpi4_sub;

    // 3. Update Table Titles & Populate Instrument Filter
    document.getElementById('tableTitle').textContent = tableData.title || "Rincian Transaksi Portofolio Pasar Uang & Nostro";
    document.getElementById('tableSubtitle').textContent = tableData.subtitle || "";
    populateInstrumentFilter(currentRecords);

    // 4. Render Table
    renderTable(currentHeaders, getFilteredDealsRecords(), data.cut_off);

    // 5. Render Charts
    renderCharts(data.charts || {});

    // 6. Render Journal
    renderJournal(currentJournalEntries);
}

// Native Canvas Chart Renderers for Offline Mode (Tanpa Akses Internet/CDN)
function drawOfflineDoughnut(canvas, labels, values) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 300;
    const height = canvas.height = canvas.parentElement.clientHeight || 280;
    ctx.clearRect(0, 0, width, height);

    const total = values.reduce((a, b) => a + Number(b || 0), 0);
    if (total === 0) return;

    const centerX = width / 2;
    const centerY = height / 2;
    const baseRadius = Math.min(centerX, centerY) - 20;
    const innerRadius = baseRadius * 0.65;
    const colors = ['#059669', '#0284c7', '#d97706', '#7c3aed', '#e11d48', '#0d9488'];

    doughnutSlices = [];
    let currentAngle = -Math.PI / 2;

    values.forEach((val, idx) => {
        const sliceAngle = (Number(val || 0) / total) * 2 * Math.PI;
        const endAngle = currentAngle + sliceAngle;
        const isHovered = (idx === doughnutHoverIdx);
        const radius = isHovered ? baseRadius + 6 : baseRadius;

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, currentAngle, endAngle);
        ctx.arc(centerX, centerY, innerRadius, endAngle, currentAngle, true);
        ctx.closePath();
        ctx.fillStyle = colors[idx % colors.length];
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = isHovered ? 3 : 2;
        ctx.stroke();

        doughnutSlices.push({
            startAngle: currentAngle,
            endAngle: endAngle,
            label: labels[idx],
            val: Number(val || 0),
            pct: ((Number(val || 0) / total) * 100).toFixed(1),
            color: colors[idx % colors.length]
        });

        currentAngle = endAngle;
    });

    renderChart1Legend(labels, values, colors, "Komposisi EAD per Jenis Instrumen");

    // Attach Interactive Hover Tooltip Listener
    if (!canvas._hasHoverListener) {
        canvas._hasHoverListener = true;
        const tooltip = document.getElementById('chartTooltip');

        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            const dx = mouseX - cx;
            const dy = mouseY - cy;
            const dist = Math.sqrt(dx * dx + dy * dy);

            const rInner = (Math.min(cx, cy) - 20) * 0.65;
            const rOuter = Math.min(cx, cy) - 10;

            if (dist >= rInner && dist <= rOuter) {
                let angle = Math.atan2(dy, dx);
                if (angle < -Math.PI / 2) angle += 2 * Math.PI;

                const foundIdx = doughnutSlices.findIndex(s => angle >= s.startAngle && angle < s.endAngle);
                if (foundIdx !== -1) {
                    if (doughnutHoverIdx !== foundIdx) {
                        doughnutHoverIdx = foundIdx;
                        drawOfflineDoughnut(canvas, labels, values);
                    }
                    const s = doughnutSlices[foundIdx];
                    if (tooltip) {
                        tooltip.style.display = 'block';
                        tooltip.style.left = (mouseX + 15) + 'px';
                        tooltip.style.top = (mouseY - 25) + 'px';
                        tooltip.innerHTML = `
                            <div class="tooltip-header">
                                <span class="tooltip-dot" style="background-color: ${s.color};"></span>
                                <span>${s.label}</span>
                            </div>
                            <div class="tooltip-body">
                                Nilai EAD: <strong>Rp ${s.val.toLocaleString('id-ID')}</strong><br>
                                Kontribusi: <strong>${s.pct}%</strong>
                            </div>
                        `;
                    }
                    return;
                }
            }

            if (doughnutHoverIdx !== -1) {
                doughnutHoverIdx = -1;
                drawOfflineDoughnut(canvas, labels, values);
                if (tooltip) tooltip.style.display = 'none';
            }
        });

        canvas.addEventListener('mouseleave', () => {
            if (doughnutHoverIdx !== -1) {
                doughnutHoverIdx = -1;
                drawOfflineDoughnut(canvas, labels, values);
            }
            if (tooltip) tooltip.style.display = 'none';
        });
    }
}

function drawOfflineBar(canvas, labels, values, chartTitle) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 300;
    const height = canvas.height = canvas.parentElement.clientHeight || 280;
    ctx.clearRect(0, 0, width, height);

    const numValues = values.map(v => Number(v || 0));
    const maxVal = Math.max(...numValues, 0);
    const titleStr = String(chartTitle || '').toLowerCase();
    const isRate = titleStr.includes('%') || titleStr.includes('rate') || titleStr.includes('pd') || (maxVal <= 1.0 && maxVal > 0);
    const isCount = titleStr.includes('jumlah') || titleStr.includes('mitra') || titleStr.includes('institusi') || titleStr.includes('item');

    const count = Math.max(numValues.length, 1);
    const isRotated = count > 5;
    const padding = { top: 30, bottom: isRotated ? 85 : 55, left: 30, right: 25 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const barWidth = Math.min(38, Math.max(12, (chartW / count) * 0.6));
    const gap = chartW / count;
    const baselineY = padding.top + chartH;

    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, baselineY);
    ctx.lineTo(padding.left + chartW, baselineY);
    ctx.stroke();

    numValues.forEach((val, idx) => {
        const barH = maxVal > 0 ? (val / maxVal) * chartH : 0;
        const x = padding.left + (idx * gap) + (gap - barWidth) / 2;
        const y = baselineY - barH;

        if (barH > 0) {
            ctx.fillStyle = 'rgba(217, 119, 6, 0.85)';
            if (ctx.roundRect) {
                ctx.beginPath();
                ctx.roundRect(x, y, barWidth, barH, [4, 4, 0, 0]);
                ctx.fill();
            } else {
                ctx.fillRect(x, y, barWidth, barH);
            }
        }

        ctx.fillStyle = val > 0 ? '#0f172a' : '#94a3b8';
        ctx.font = '600 10px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        
        let displayVal;
        if (isRate) {
            const pctVal = val > 1.0 ? val : val * 100;
            displayVal = pctVal.toFixed(2) + '%';
        } else if (isCount) {
            displayVal = val.toLocaleString('id-ID') + ' Mitra';
        } else if (val >= 1000000000) {
            displayVal = (val / 1000000000).toFixed(2) + ' M';
        } else if (val >= 1000000) {
            displayVal = (val / 1000000).toFixed(1) + ' Jt';
        } else if (val > 0) {
            displayVal = 'Rp ' + val.toLocaleString('id-ID');
        } else {
            displayVal = isRate ? '0.00%' : 'Rp 0';
        }

        if (count <= 12) {
            ctx.fillText(displayVal, x + barWidth / 2, y - 6);
        }

        ctx.save();
        ctx.fillStyle = '#475569';
        ctx.font = '600 10px Inter, sans-serif';
        const lbl = String(labels[idx] || '');
        const centerX = x + barWidth / 2;
        const labelY = baselineY + 8;

                if (isRotated) {
            ctx.translate(centerX, labelY);
            ctx.rotate(-Math.PI / 4);
            ctx.textAlign = 'right';
            ctx.textBaseline = 'top';
            ctx.fillText(lbl, 0, 0);
        } else {
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            // Word-wrap multiline agar nama lengkap institusi tidak terpotong sama sekali
            const maxWidth = Math.max(gap - 10, 70);
            const words = lbl.split(' ');
            const lines = [];
            let curLine = '';
            for (let w = 0; w < words.length; w++) {
                const testLine = curLine ? curLine + ' ' + words[w] : words[w];
                if (ctx.measureText(testLine).width > maxWidth && curLine) {
                    lines.push(curLine);
                    curLine = words[w];
                } else {
                    curLine = testLine;
                }
            }
            if (curLine) lines.push(curLine);

            lines.forEach((lineText, lIdx) => {
                ctx.fillText(lineText, centerX, labelY + (lIdx * 13));
            });
        }
        ctx.restore();
    });
}

// Render Chart 2 with Top N Filter
function applyChart2FilterAndRender() {
    const c2Title = document.getElementById('chart2Title');
    const c2Tag = document.getElementById('chart2Tag');
    const c2Canvas = document.getElementById('chartCounterparty');
    const c2Empty = document.getElementById('chart2Empty');

    c2Title.textContent = rawChart2Title;
    c2Tag.textContent = rawChart2Tag;

    const entries = Object.entries(rawChart2Data || {});
    if (entries.length === 0) {
        c2Canvas.style.display = 'none';
        if (c2Empty) c2Empty.style.display = 'flex';
        if (chartCounterpartyInstance && typeof chartCounterpartyInstance.destroy === 'function') {
            chartCounterpartyInstance.destroy();
            chartCounterpartyInstance = null;
        }
        return;
    }

    c2Canvas.style.display = 'block';
    if (c2Empty) c2Empty.style.display = 'none';

    entries.sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));

    let filteredEntries = entries;
    if (chart2FilterMode !== 'all') {
        const topLimit = parseInt(chart2FilterMode) || 10;
        filteredEntries = entries.slice(0, topLimit);
    }

    const labels2 = filteredEntries.map(e => e[0]);
    const values2 = filteredEntries.map(e => Number(e[1] || 0));

    const titleStr = rawChart2Title.toLowerCase();
    const isRate = titleStr.includes('%') || titleStr.includes('rate') || titleStr.includes('pd');

    if (typeof Chart !== 'undefined') {
        const ctx2 = c2Canvas.getContext('2d');
        if (chartCounterpartyInstance && typeof chartCounterpartyInstance.destroy === 'function') {
            chartCounterpartyInstance.destroy();
        }

        chartCounterpartyInstance = new Chart(ctx2, {
            type: 'bar',
            data: {
                labels: labels2,
                datasets: [{
                    label: isRate ? 'TTC PD Rate (%)' : 'Beban CKPN (Rp)',
                    data: values2,
                    backgroundColor: 'rgba(217, 119, 6, 0.85)',
                    borderColor: '#b45309',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        bottom: labels2.length > 6 ? 20 : 0
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#475569',
                            font: { family: 'Inter', size: labels2.length > 10 ? 9 : 10, weight: '600' },
                            maxRotation: labels2.length > 6 ? 45 : 0,
                            minRotation: labels2.length > 6 ? 30 : 0,
                            autoSkip: false,
                            callback: function(val, index) {
                                const label = this.getLabelForValue(val) || '';
                                return label.length > 18 ? label.substring(0, 16) + '…' : label;
                            }
                        },
                        grid: { display: false }
                    },
                    y: {
                        ticks: {
                            color: '#475569',
                            font: { family: 'JetBrains Mono', size: 10 },
                            callback: function (val) {
                                if (isRate) return val.toFixed(1) + '%';
                                if (val >= 1000000000) return (val / 1000000000).toFixed(1) + ' M';
                                if (val >= 1000000) return (val / 1000000).toFixed(1) + ' Jt';
                                if (val >= 1000) return (val / 1000).toFixed(0) + ' Rb';
                                return val;
                            }
                        },
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        titleColor: '#ffffff',
                        titleFont: { family: 'Inter', size: 12, weight: 'bold' },
                        bodyColor: '#fbbf24',
                        bodyFont: { family: 'JetBrains Mono', size: 12 },
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            label: function (ctx) {
                                const val = Number(ctx.parsed.y || 0);
                                if (isRate) {
                                    const pctVal = val > 1.0 ? val : val * 100;
                                    return ` TTC PD Rate: ${pctVal.toFixed(4)}%`;
                                }
                                return ' ' + ctx.dataset.label + ': ' + (val > 1000 ? formatRupiah(val) : val);
                            }
                        }
                    }
                }
            }
        });
    } else {
        drawOfflineBar(c2Canvas, labels2, values2, rawChart2Title);
    }
}

let lastChartsData = null;

// Render Charts Dynamically
function renderCharts(chartsData) {
    lastChartsData = chartsData;
    const c1Title = document.getElementById('chart1Title');
    const c1Tag = document.getElementById('chart1Tag');
    const c1Canvas = document.getElementById('chartInstruments');
    const c1Empty = document.getElementById('chart1Empty');
    const c1Legend = document.getElementById('chart1Legend');
    c1Title.textContent = chartsData.chart1_title || "Komposisi EAD per Jenis Instrumen";
    c1Tag.textContent = chartsData.chart1_tag || "FASBIS • PUAS • Nostro";

    const c1Data = chartsData.chart1_data || {};
    const labels1 = Object.keys(c1Data);
    const values1 = Object.values(c1Data);
    const hasData1 = labels1.length > 0;

    if (!hasData1) {
        c1Canvas.style.display = 'none';
        if (c1Empty) c1Empty.style.display = 'flex';
        if (c1Legend) c1Legend.style.display = 'none';
        if (chartInstInstance && typeof chartInstInstance.destroy === 'function') {
            chartInstInstance.destroy();
            chartInstInstance = null;
        }
    } else {
        c1Canvas.style.display = 'block';
        if (c1Empty) c1Empty.style.display = 'none';

        const chartColors = ['#059669', '#0284c7', '#d97706', '#7c3aed', '#e11d48', '#0d9488'];
        renderChart1Legend(labels1, values1, chartColors, chartsData.chart1_title);

        if (typeof Chart !== 'undefined') {
            const ctx1 = c1Canvas.getContext('2d');
            if (chartInstInstance && typeof chartInstInstance.destroy === 'function') chartInstInstance.destroy();

            chartInstInstance = new Chart(ctx1, {
                type: 'doughnut',
                data: {
                    labels: labels1,
                    datasets: [{
                        data: values1,
                        backgroundColor: chartColors,
                        borderColor: '#ffffff',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.95)',
                            titleColor: '#ffffff',
                            titleFont: { family: 'Inter', size: 12, weight: 'bold' },
                            bodyColor: '#38bdf8',
                            bodyFont: { family: 'JetBrains Mono', size: 12 },
                            padding: 10,
                            cornerRadius: 8,
                            displayColors: true,
                            callbacks: {
                                label: function (ctx) {
                                    const val = Number(ctx.parsed || 0);
                                    const total = ctx.dataset.data.reduce((a, b) => a + Number(b || 0), 0);
                                    const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0.0';
                                    return ` EAD: ${formatRupiah(val)} (${pct}%)`;
                                }
                            }
                        }
                    },
                    cutout: '66%'
                }
            });
        } else {
            drawOfflineDoughnut(c1Canvas, labels1, values1);
        }
    }

    rawChart2Data = chartsData.chart2_data || {};
    rawChart2Title = chartsData.chart2_title || "Distribusi Beban CKPN per Pihak Lawan";
    rawChart2Tag = chartsData.chart2_tag || "Counterparty Risk";
    applyChart2FilterAndRender();
}

// Render Pagination Bar Component
function renderPaginationBar(container, totalItems, pageSize, currentPage, totalPages, startIdx, endIdx, onPageChange) {
    if (totalItems <= 0) {
        container.innerHTML = '';
        return;
    }

    const showingText = `Menampilkan ${startIdx + 1}-${endIdx} dari ${totalItems} baris`;

    let buttonsHtml = '';
    buttonsHtml += `<button type="button" class="btn-page" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&laquo; Prev</button>`;

    for (let p = 1; p <= totalPages; p++) {
        if (totalPages > 7) {
            if (p !== 1 && p !== totalPages && Math.abs(p - currentPage) > 1) {
                if (p === 2 || p === totalPages - 1) {
                    buttonsHtml += `<span style="padding: 0 4px; color: #94a3b8; align-self: center;">...</span>`;
                }
                continue;
            }
        }
        buttonsHtml += `<button type="button" class="btn-page ${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
    }

    buttonsHtml += `<button type="button" class="btn-page ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Next &raquo;</button>`;

    container.innerHTML = `
        <span class="pagination-info">${showingText}</span>
        <div class="pagination-controls">${buttonsHtml}</div>
    `;

    container.querySelectorAll('button[data-page]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetPage = parseInt(e.currentTarget.getAttribute('data-page'));
            if (targetPage && targetPage >= 1 && targetPage <= totalPages && targetPage !== currentPage) {
                onPageChange(targetPage);
            }
        });
    });
}

// Render Table Headers and Body with Pagination (DDR 5, 10, 25, 50, 100)
function formatDisplayDate(dateStr) {
    if (!dateStr) return '-';
    if (dateStr.includes('/')) return dateStr;
    const parts = dateStr.split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
}

function renderTable(headers, records, cutOff) {
    const thead = document.getElementById('dealsTableHead');
    const tbody = document.getElementById('dealsTableBody');
    const counter = document.getElementById('recordCounter');
    const paginationEl = document.getElementById('dealsPagination');

    thead.innerHTML = '';
    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    tbody.innerHTML = '';
    if (counter) counter.textContent = `${records.length} Baris Data`;

    if (records.length === 0) {
        const searchVal = document.getElementById('searchInput')?.value?.trim();
        const filterVal = document.getElementById('filterInstrument')?.value?.trim();
        const isFiltered = Boolean(searchVal || filterVal);

        const emptyMessage = isFiltered
            ? 'Tidak ada data transaksi yang cocok dengan filter yang dipilih.'
            : `Belum ada data kalkulasi untuk tanggal ${formatDisplayDate(cutOff)}.`;

        tbody.innerHTML = `
            <tr>
                <td colspan="${headers.length || 11}" class="text-center py-5" style="color: #64748b; font-size: 0.95rem;">
                    <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">${isFiltered ? '🔍' : '📁'}</div>
                    <strong>${emptyMessage}</strong>
                    ${isFiltered ? '<br><span style="font-size: 0.8rem; color: #94a3b8;">Silakan ubah pilihan Instrumen atau kata kunci pencarian Anda.</span>' : ''}
                </td>
            </tr>
        `;
        if (paginationEl) paginationEl.innerHTML = '';
        return;
    }

    const totalRecords = records.length;
    const totalPages = Math.ceil(totalRecords / dealsPageSize) || 1;
    if (dealsCurrentPage > totalPages) dealsCurrentPage = totalPages;
    if (dealsCurrentPage < 1) dealsCurrentPage = 1;

    const startIdx = (dealsCurrentPage - 1) * dealsPageSize;
    const endIdx = Math.min(startIdx + dealsPageSize, totalRecords);
    const pageRecords = records.slice(startIdx, endIdx);

    pageRecords.forEach(row => {
        const tr = document.createElement('tr');
        const stageNum = parseInt(row.col7) || 1;
        const stageBadgeClass = stageNum === 1 ? 'badge-stage-1' : 'badge-stage-2';
        const stageLabel = stageNum === 1 ? 'Stage 1 (Lancar)' : 'Stage 2 (Warning)';

        const val5 = typeof row.col5 === 'number' ? formatRupiah(row.col5) : row.col5;
        const val11 = typeof row.col11 === 'number' ? formatRupiah(row.col11) : row.col11;

        tr.innerHTML = `
            <td class="mono-cell" style="font-weight: 700; color: #0284c7;">${row.col1}</td>
            <td><strong style="color: #0f172a;">${row.col2}</strong></td>
            <td><span class="badge-instrument">${row.col3}</span></td>
            <td class="mono-cell" style="font-weight: 500;">${row.col4}</td>
            <td class="mono-cell" style="font-weight: 700; color: #0f172a;">${val5}</td>
            <td><span class="badge-rating">${row.col6}</span></td>
            <td><span class="badge-stage ${stageBadgeClass}">${stageLabel}</span></td>
            <td class="mono-cell">${row.col8}</td>
            <td class="mono-cell" style="color: #047857; font-weight: 600;">${row.col9}</td>
            <td class="mono-cell">${row.col10}</td>
            <td class="mono-cell" style="font-weight: 800; color: #b45309;">${val11}</td>
        `;
        tbody.appendChild(tr);
    });

    if (paginationEl) {
        renderPaginationBar(paginationEl, totalRecords, dealsPageSize, dealsCurrentPage, totalPages, startIdx, endIdx, (newPage) => {
            dealsCurrentPage = newPage;
            renderTable(headers, records, cutOff);
        });
    }
}

// Render Accounting Journal with Pagination (DDR 5, 10, 25, 50, 100)
function renderJournal(entries) {
    const tbody = document.getElementById('journalTableBody');
    const paginationEl = document.getElementById('journalPagination');
    tbody.innerHTML = '';

    const validEntries = (entries || []).filter(e => Number(e.nominal || 0) > 0);
    if (validEntries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">Belum ada ayat jurnal untuk modul ini.</td></tr>`;
        if (paginationEl) paginationEl.innerHTML = '';
        return;
    }

    const totalEntries = validEntries.length;
    const totalPages = Math.ceil(totalEntries / journalPageSize) || 1;
    if (journalCurrentPage > totalPages) journalCurrentPage = totalPages;
    if (journalCurrentPage < 1) journalCurrentPage = 1;

    const startIdx = (journalCurrentPage - 1) * journalPageSize;
    const endIdx = Math.min(startIdx + journalPageSize, totalEntries);
    const pageEntries = validEntries.slice(startIdx, endIdx);

    pageEntries.forEach(entry => {
        const tr = document.createElement('tr');
        const isDebit = entry.posisi === 'DEBIT';
        const isStatus = entry.posisi === 'STATUS';

        let debitVal = '-';
        let creditVal = '-';

        if (isStatus) {
            debitVal = `${entry.nominal} Item`;
            creditVal = `Tersinkronisasi`;
        } else {
            debitVal = isDebit ? formatRupiah(entry.nominal) : '-';
            creditVal = !isDebit ? formatRupiah(entry.nominal) : '-';
        }

        const indentStyle = !isDebit && !isStatus ? 'padding-left: 2rem;' : '';
        const badgeColor = isDebit ? '#047857' : (isStatus ? '#0284c7' : '#b45309');

        tr.innerHTML = `
            <td class="mono-cell" style="font-weight: 700; color: #0f172a;">${entry.kode_akun}</td>
            <td style="${indentStyle} color: #334155; font-weight: 500;">${entry.nama_akun}</td>
            <td><strong style="color: ${badgeColor};">${entry.posisi}</strong></td>
            <td class="text-right mono-cell" style="font-weight: 700; color: #0f172a;">${debitVal}</td>
            <td class="text-right mono-cell" style="font-weight: 700; color: #0f172a;">${creditVal}</td>
        `;
        tbody.appendChild(tr);
    });

    if (paginationEl) {
        renderPaginationBar(paginationEl, totalEntries, journalPageSize, journalCurrentPage, totalPages, startIdx, endIdx, (newPage) => {
            journalCurrentPage = newPage;
            renderJournal(entries);
        });
    }
}

// Filter Deals by Search Query and Selected Instrument
function getFilteredDealsRecords() {
    const q = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
    const instFilter = (document.getElementById('filterInstrument')?.value || '').trim();

    return currentRecords.filter(r => {
        const matchesQuery = !q || (
            (r.col1 && String(r.col1).toLowerCase().includes(q)) ||
            (r.col2 && String(r.col2).toLowerCase().includes(q)) ||
            (r.col3 && String(r.col3).toLowerCase().includes(q))
        );
        const matchesInstrument = !instFilter || (
            r.col3 && String(r.col3).trim() === instFilter
        );
        return matchesQuery && matchesInstrument;
    });
}

// Populate Instrument Options Dynamically from Current Records
function populateInstrumentFilter(records) {
    const filterEl = document.getElementById('filterInstrument');
    if (!filterEl) return;
    const currentVal = filterEl.value;

    const instruments = [...new Set(records.map(r => r.col3).filter(Boolean))].sort();

    let html = '<option value="">Semua Instrumen</option>';
    instruments.forEach(inst => {
        const isSelected = (inst === currentVal) ? 'selected' : '';
        html += `<option value="${inst}" ${isSelected}>${inst}</option>`;
    });

    filterEl.innerHTML = html;
}

// Search Filter Handler
const searchInputEl = document.getElementById('searchInput');
if (searchInputEl) {
    searchInputEl.addEventListener('input', function () {
        dealsCurrentPage = 1;
        renderTable(currentHeaders, getFilteredDealsRecords(), document.getElementById('cutOffDate').value);
    });
}

// Dropdown Instrument Filter Handler
const filterInstrumentEl = document.getElementById('filterInstrument');
if (filterInstrumentEl) {
    filterInstrumentEl.addEventListener('change', function () {
        dealsCurrentPage = 1;
        renderTable(currentHeaders, getFilteredDealsRecords(), document.getElementById('cutOffDate').value);
    });
}

// DDR Page Size Selector Handlers
const pageSizeDealsEl = document.getElementById('pageSizeDeals');
if (pageSizeDealsEl) {
    pageSizeDealsEl.addEventListener('change', (e) => {
        dealsPageSize = parseInt(e.target.value) || 10;
        dealsCurrentPage = 1;
        renderTable(currentHeaders, getFilteredDealsRecords(), document.getElementById('cutOffDate').value);
    });
}

const pageSizeJournalEl = document.getElementById('pageSizeJournal');
if (pageSizeJournalEl) {
    pageSizeJournalEl.addEventListener('change', (e) => {
        journalPageSize = parseInt(e.target.value) || 5;
        journalCurrentPage = 1;
        renderJournal(currentJournalEntries);
    });
}

// Chart 2 Top N Filter Handler
const chart2TopFilterEl = document.getElementById('chart2TopFilter');
if (chart2TopFilterEl) {
    chart2TopFilterEl.addEventListener('change', (e) => {
        chart2FilterMode = e.target.value;
        applyChart2FilterAndRender();
    });
}

// =====================================================================
// MODAL KONFIRMASI (MOCKUP KONFIRMASI SEBELUM RUN ENGINE)
// =====================================================================
function openConfirmModal() {
    const cutOff = document.getElementById('cutOffDate')?.value || '-';
    const displayEl = document.getElementById('modalCutOffDisplay');
    if (displayEl) {
        if (cutOff.includes('-')) {
            const parts = cutOff.split('-');
            displayEl.textContent = `${parts[2]}/${parts[1]}/${parts[0]}`;
        } else {
            displayEl.textContent = cutOff;
        }
    }
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.add('active');
}

function closeConfirmModal() {
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.remove('active');
}

// Event Listeners:
const btnRunEngineEl = document.getElementById('btnRunEngine');
if (btnRunEngineEl) {
    btnRunEngineEl.addEventListener('click', openConfirmModal);
}

const btnCancelModalEl = document.getElementById('btnCancelModal');
if (btnCancelModalEl) {
    btnCancelModalEl.addEventListener('click', closeConfirmModal);
}

const btnConfirmRunEl = document.getElementById('btnConfirmRun');
if (btnConfirmRunEl) {
    btnConfirmRunEl.addEventListener('click', () => {
        closeConfirmModal();
        runEngine();
    });
}

// Tutup modal jika klik di area overlay gelap
const confirmModalEl = document.getElementById('confirmModal');
if (confirmModalEl) {
    confirmModalEl.addEventListener('click', (e) => {
        if (e.target === confirmModalEl) {
            closeConfirmModal();
        }
    });
}

// Tutup modal jika menekan tombol Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeConfirmModal();
    }
});


// Auto-load data saat user mengganti tanggal cut-off di date picker
const cutOffDateInputEl = document.getElementById('cutOffDate');
if (cutOffDateInputEl) {
    cutOffDateInputEl.addEventListener('change', async (e) => {
        const newCutoff = e.target.value;
        if (!newCutoff) return;
        const searchEl = document.getElementById('searchInput');
        if (searchEl) searchEl.value = '';
        const filterInstEl = document.getElementById('filterInstrument');
        if (filterInstEl) filterInstEl.value = '';

        dealsCurrentPage = 1;
        await fetchAndRenderData(newCutoff);
    });
}

// Initialization:
document.addEventListener('DOMContentLoaded', async () => {
    checkSystemStatus();
    let initialCutoff = '2026-10-31';
    try {
        const res = await fetch('/api/module-cutoff?module=interbank');
        if (res.ok) {
            const data = await res.json();
            if (data.latest_cutoff) {
                initialCutoff = data.latest_cutoff;
                document.getElementById('cutOffDate').value = initialCutoff;
            }
        }
    } catch (e) {
        console.warn('Gagal membaca cut-off interbank:', e);
    }
    const currentCutoff = document.getElementById('cutOffDate').value || initialCutoff;
    await fetchAndRenderData(currentCutoff);
});

// Window Resize Responsive Redraw for Full Width:
let resizeTimer;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (lastChartsData) {
            renderCharts(lastChartsData);
        }
    }, 150);
});
