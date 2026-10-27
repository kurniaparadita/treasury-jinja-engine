// State Variables
let chartInstInstance = null;
let chartCounterpartyInstance = null;
let currentRecords = [];
let currentHeaders = [];

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
        
        // 1. Update Nama Bank dari Ref_NamaBank (Poin 3)
        if (data.bank_name) {
            document.getElementById('bankNameTitle').textContent = data.bank_name;
            document.getElementById('footerText').innerHTML = `Dashboard PSAK 413 &bull; ${data.bank_name}`;
        }

        // 2. Update Alert Banner jika database belum terhubung
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

// Run Engine API
async function runEngine() {
    const btn = document.getElementById('btnRunEngine');
    const btnText = document.getElementById('btnText');
    const cutOff = document.getElementById('cutOffDate').value;
    const module = document.getElementById('moduleSelect').value;

    btn.disabled = true;
    btnText.textContent = 'Mengeksekusi...';

    try {
        const response = await fetch('/api/run-engine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cut_off: cutOff,
                module: module
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

// Update DOM with Engine Output
function updateDashboard(data) {
    const summary = data.summary;
    const tableData = data.table || {};
    currentRecords = tableData.records || [];
    currentHeaders = tableData.headers || [];

    // 1. Update Nama Bank jika ada
    if (data.bank_name) {
        document.getElementById('bankNameTitle').textContent = data.bank_name;
    }

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

    // 3. Update Table Titles
    document.getElementById('tableTitle').textContent = tableData.title || "Data Portofolio Riil";
    document.getElementById('tableSubtitle').textContent = tableData.subtitle || "";

    // 4. Render Table
    renderTable(currentHeaders, currentRecords, data.cut_off);

    // 5. Render Charts
    renderCharts(data.charts || {});

    // 6. Render Journal
    renderJournal(data.journal || []);
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
    const centerY = (height / 2) - 15;
    const radius = Math.min(centerX, centerY) - 20;
    const innerRadius = radius * 0.65;
    const colors = ['#059669', '#0284c7', '#d97706', '#7c3aed', '#e11d48', '#0d9488'];

    let currentAngle = -Math.PI / 2;
    values.forEach((val, idx) => {
        const sliceAngle = (Number(val || 0) / total) * 2 * Math.PI;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
        ctx.arc(centerX, centerY, innerRadius, currentAngle + sliceAngle, currentAngle, true);
        ctx.closePath();
        ctx.fillStyle = colors[idx % colors.length];
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
        currentAngle += sliceAngle;
    });

    // Legend
    ctx.font = '600 11px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#475569';
    const legendText = labels.slice(0, 5).map((l, i) => `${l}: ${values[i]}`).join('  |  ');
    ctx.fillText(legendText, centerX, height - 12);
}

function drawOfflineBar(canvas, labels, values) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.parentElement.clientWidth || 300;
    const height = canvas.height = canvas.parentElement.clientHeight || 280;
    ctx.clearRect(0, 0, width, height);

    const numValues = values.map(v => Number(v || 0));
    const maxVal = Math.max(...numValues, 1);
    const padding = { top: 25, bottom: 35, left: 35, right: 20 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const barWidth = Math.min(45, (chartW / Math.max(numValues.length, 1)) * 0.65);
    const gap = chartW / Math.max(numValues.length, 1);

    numValues.forEach((val, idx) => {
        const barH = (val / maxVal) * chartH;
        const x = padding.left + (idx * gap) + (gap - barWidth) / 2;
        const y = padding.top + chartH - barH;

        ctx.fillStyle = 'rgba(217, 119, 6, 0.85)';
        if (ctx.roundRect) {
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barH, [4, 4, 0, 0]);
            ctx.fill();
        } else {
            ctx.fillRect(x, y, barWidth, barH);
        }

        ctx.fillStyle = '#0f172a';
        ctx.font = '600 10px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        const displayVal = val >= 1000 ? (val / 1000).toFixed(0) + 'k' : val.toFixed(1) + '%';
        ctx.fillText(displayVal, x + barWidth / 2, y - 6);

        ctx.fillStyle = '#64748b';
        ctx.font = '600 10px Inter, sans-serif';
        const lbl = String(labels[idx] || '').substring(0, 10);
        ctx.fillText(lbl, x + barWidth / 2, height - 12);
    });
}

// Render Charts Dynamically (Mendukung Online & Offline Tanpa Internet)
function renderCharts(chartsData) {
    // ----------------------------------------------------
    // Chart 1: Portofolio / Rating Distribution
    // ----------------------------------------------------
    const c1Title = document.getElementById('chart1Title');
    const c1Tag = document.getElementById('chart1Tag');
    const c1Canvas = document.getElementById('chartInstruments');
    const c1Empty = document.getElementById('chart1Empty');
    c1Title.textContent = chartsData.chart1_title || "Distribusi Portofolio";
    c1Tag.textContent = chartsData.chart1_tag || "Data Riil";

    const c1Data = chartsData.chart1_data || {};
    const labels1 = Object.keys(c1Data);
    const values1 = Object.values(c1Data);
    const hasData1 = labels1.length > 0;

    if (!hasData1) {
        c1Canvas.style.display = 'none';
        if (c1Empty) c1Empty.style.display = 'flex';
        if (chartInstInstance && typeof chartInstInstance.destroy === 'function') {
            chartInstInstance.destroy();
            chartInstInstance = null;
        }
    } else {
        c1Canvas.style.display = 'block';
        if (c1Empty) c1Empty.style.display = 'none';

        if (typeof Chart !== 'undefined') {
            const ctx1 = c1Canvas.getContext('2d');
            if (chartInstInstance && typeof chartInstInstance.destroy === 'function') chartInstInstance.destroy();

            chartInstInstance = new Chart(ctx1, {
                type: 'doughnut',
                data: {
                    labels: labels1,
                    datasets: [{
                        data: values1,
                        backgroundColor: ['#059669', '#0284c7', '#d97706', '#7c3aed', '#e11d48'],
                        borderColor: '#ffffff',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#475569', font: { family: 'Inter', size: 11, weight: '600' } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    const val = ctx.parsed;
                                    return ' ' + ctx.label + ': ' + (val > 1000 ? formatRupiah(val) : val);
                                }
                            }
                        }
                    },
                    cutout: '66%'
                }
            });
        } else {
            // Fallback Offline: Gunakan Native Canvas Renderer
            drawOfflineDoughnut(c1Canvas, labels1, values1);
        }
    }

    // ----------------------------------------------------
    // Chart 2: Risiko / PD Rate Distribution
    // ----------------------------------------------------
    const c2Title = document.getElementById('chart2Title');
    const c2Tag = document.getElementById('chart2Tag');
    const c2Canvas = document.getElementById('chartCounterparty');
    const c2Empty = document.getElementById('chart2Empty');
    c2Title.textContent = chartsData.chart2_title || "Distribusi Risiko";
    c2Tag.textContent = chartsData.chart2_tag || "Data Riil";

    const c2Data = chartsData.chart2_data || {};
    const labels2 = Object.keys(c2Data);
    const values2 = Object.values(c2Data);
    const hasData2 = labels2.length > 0;

    if (!hasData2) {
        c2Canvas.style.display = 'none';
        if (c2Empty) c2Empty.style.display = 'flex';
        if (chartCounterpartyInstance && typeof chartCounterpartyInstance.destroy === 'function') {
            chartCounterpartyInstance.destroy();
            chartCounterpartyInstance = null;
        }
    } else {
        c2Canvas.style.display = 'block';
        if (c2Empty) c2Empty.style.display = 'none';

        if (typeof Chart !== 'undefined') {
            const ctx2 = c2Canvas.getContext('2d');
            if (chartCounterpartyInstance && typeof chartCounterpartyInstance.destroy === 'function') chartCounterpartyInstance.destroy();

            chartCounterpartyInstance = new Chart(ctx2, {
                type: 'bar',
                data: {
                    labels: labels2,
                    datasets: [{
                        label: 'Nilai Riil',
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
                    scales: {
                        x: {
                            ticks: { color: '#475569', font: { family: 'Inter', size: 11, weight: '600' } },
                            grid: { display: false }
                        },
                        y: {
                            ticks: {
                                color: '#475569',
                                font: { family: 'JetBrains Mono', size: 10 },
                                callback: function (val) {
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
                            callbacks: {
                                label: function (ctx) {
                                    const val = ctx.parsed.y;
                                    return ' ' + ctx.dataset.label + ': ' + (val > 1000 ? formatRupiah(val) : val);
                                }
                            }
                        }
                    }
                }
            });
        } else {
            // Fallback Offline: Gunakan Native Canvas Renderer
            drawOfflineBar(c2Canvas, labels2, values2);
        }
    }
}

// Render Table Headers and Body
function renderTable(headers, records, cutOff) {
    const thead = document.getElementById('dealsTableHead');
    const tbody = document.getElementById('dealsTableBody');
    const counter = document.getElementById('recordCounter');

    // 1. Render Headers
    thead.innerHTML = '';
    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    // 2. Render Records
    tbody.innerHTML = '';
    counter.textContent = `${records.length} Baris Data`;

    if (records.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="${headers.length || 11}" class="text-center py-5" style="color: #64748b; font-size: 0.9rem;">
                    <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📭</div>
                    <strong>Tidak ada data ditemukan pada database untuk modul ini (Cut-off: ${cutOff || '-'}).</strong><br>
                    <span style="font-size: 0.8rem; color: #94a3b8;">Pastikan tabel staging / master pada database SQL Server telah terisi dan koneksi jaringan/VPN aktif.</span>
                </td>
            </tr>
        `;
        return;
    }

    records.forEach(row => {
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
}

// Render Accounting Journal
function renderJournal(entries) {
    const tbody = document.getElementById('journalTableBody');
    tbody.innerHTML = '';

    if (entries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-3 text-muted">Belum ada ayat jurnal untuk modul ini.</td></tr>`;
        return;
    }

    entries.forEach(entry => {
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
}

// Search Filter Handler
document.getElementById('searchInput').addEventListener('input', function (e) {
    const q = e.target.value.toLowerCase();
    const filtered = currentRecords.filter(r => 
        (r.col1 && String(r.col1).toLowerCase().includes(q)) ||
        (r.col2 && String(r.col2).toLowerCase().includes(q)) ||
        (r.col3 && String(r.col3).toLowerCase().includes(q))
    );
    renderTable(currentHeaders, filtered, document.getElementById('cutOffDate').value);
});

// Dropdown Change Handler: Otomatis membaca tanggal cut-off dari tabel database modul terkait & mengeksekusi query
async function onModuleChange() {
    const selectedModule = document.getElementById('moduleSelect').value;
    const cutOffInput = document.getElementById('cutOffDate');

    try {
        // 1. Ambil tanggal cut-off terakhir dari tabel database fact/master modul terpilih
        const res = await fetch(`/api/module-cutoff?module=${encodeURIComponent(selectedModule)}`);
        if (res.ok) {
            const data = await res.json();
            if (data.latest_cutoff) {
                cutOffInput.value = data.latest_cutoff;
            }
        }
    } catch (e) {
        console.warn('Gagal membaca tanggal cut-off modul dari database:', e);
    }

    // 2. Jalankan eksekusi kalkulasi sesuai modul dan tanggal cut-off baru
    await runEngine();
}

// Event Listeners:
// a. Saat dropdown modul berganti -> otomatis update tanggal cut-off dari tabel modul & jalankan query
document.getElementById('moduleSelect').addEventListener('change', onModuleChange);

// b. Saat tanggal cut-off diubah manual oleh user -> jalankan ulang kalkulasi
document.getElementById('cutOffDate').addEventListener('change', runEngine);

// c. Tombol "Jalankan Kalkulasi"
document.getElementById('btnRunEngine').addEventListener('click', runEngine);

// Initialization: Poin 5 (Default ke urutan pertama: counterparty)
document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('moduleSelect').value = "counterparty";
    checkSystemStatus();
    await onModuleChange();
});
