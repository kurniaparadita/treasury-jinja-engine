/**
 * Logika Frontend Khusus Modul 1: Master Counterparty Harmonization (PSAK 413)
 * PIC: Ahmad
 */

// State Mandiri Modul Counterparty
let cpAllRecords = [];
let cpFilteredRecords = [];
let cpCurrentPage = 1;
const cpPageSize = 10;

function getRatingBadge(agency, rating) {
    const ag = String(agency || '').toUpperCase();
    if (ag.includes('SOVEREIGN')) {
        return `<span style="background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.3px; display: inline-block;">SOVEREIGN</span>`;
    }
    if (ag.includes('PEFINDO')) {
        return `<span style="background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.3px; display: inline-block;">PEFINDO</span>`;
    }
    if (ag.includes('FITCH')) {
        return `<span style="background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.3px; display: inline-block;">FITCH</span>`;
    }
    if (ag.includes('INTERNAL')) {
        return `<span style="background: #faf5ff; color: #7e22ce; border: 1px solid #e9d5ff; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.3px; display: inline-block;">INTERNAL</span>`;
    }
    return `<span style="background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 11.5px; display: inline-block;">${agency || 'UNRATED'}</span>`;
}

function getInvestmentGradeBadge(grade) {
    const g = String(grade || '').toUpperCase();
    if (g.includes('INVESTMENT') && !g.includes('NON')) {
        return `<span style="background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 11.5px; display: inline-flex; align-items: center; gap: 6px;"><span style="width: 7px; height: 7px; border-radius: 50%; background: #10b981;"></span>INVESTMENT GRADE</span>`;
    }
    return `<span style="background: #fffbeb; color: #b45309; border: 1px solid #fde68a; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 11.5px; display: inline-flex; align-items: center; gap: 6px;"><span style="width: 7px; height: 7px; border-radius: 50%; background: #f59e0b;"></span>NON-INVESTMENT GRADE</span>`;
}

// Inisialisasi atau Update Dashboard Counterparty dari data JSON
window.renderCounterpartyModule = function(data) {
    const summary = data.summary || {};
    const tableData = data.table || {};

    // 1. Update 4 KPI Cards Ahmad (Tanpa Simbol Rupiah)
    const kpiTotal = document.getElementById('cpKpiTotal');
    const kpiSovereign = document.getElementById('cpKpiSovereign');
    const kpiIg = document.getElementById('cpKpiIg');
    const kpiUnrated = document.getElementById('cpKpiUnrated');

    if (kpiTotal) kpiTotal.textContent = summary.kpi1_val || "0 Entitas";
    if (kpiSovereign) kpiSovereign.textContent = summary.kpi2_val || "0 Entitas";
    if (kpiIg) kpiIg.textContent = (summary.kpi3_s1 || 0) + " Entitas";
    if (kpiUnrated) kpiUnrated.textContent = summary.kpi4_val || "0 Entitas";

    // 2. Simpan record master
    cpAllRecords = tableData.records || [];
    cpCurrentPage = 1;

    // 3. Terapkan filter & render tabel
    filterAndRenderCpTable();
};

function filterAndRenderCpTable() {
    const searchVal = (document.getElementById('cpSearchInput')?.value || '').toLowerCase().trim();
    const catVal = (document.getElementById('cpCategoryFilter')?.value || '').trim();

    cpFilteredRecords = cpAllRecords.filter(r => {
        const matchSearch = !searchVal || 
            String(r.col1 || '').toLowerCase().includes(searchVal) ||
            String(r.col2 || '').toLowerCase().includes(searchVal);
        const matchCat = !catVal || String(r.col6 || '').toUpperCase() === catVal.toUpperCase();
        return matchSearch && matchCat;
    });

    renderCpTablePage();
}

function renderCpTablePage() {
    const tbody = document.getElementById('cpTableBody');
    const counter = document.getElementById('cpRecordCounter');
    const paginationBar = document.getElementById('cpPaginationBar');
    if (!tbody) return;

    const totalRecords = cpFilteredRecords.length;
    const totalPages = Math.max(1, Math.ceil(totalRecords / cpPageSize));
    if (cpCurrentPage > totalPages) cpCurrentPage = totalPages;
    if (cpCurrentPage < 1) cpCurrentPage = 1;

    const startIdx = (cpCurrentPage - 1) * cpPageSize;
    const endIdx = Math.min(startIdx + cpPageSize, totalRecords);
    const pageRecords = cpFilteredRecords.slice(startIdx, endIdx);

    if (counter) {
        counter.textContent = `${totalRecords} Data`;
    }

    // Render Table Rows (7 Kolom dim_counterparty_harmonized) dengan Spacing Lega
    tbody.innerHTML = '';
    if (pageRecords.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-5 text-muted" style="text-align: center; padding: 3rem 1.5rem;">
                    <div style="font-size: 2rem; margin-bottom: 0.5rem;">📭</div>
                    <strong>Tidak ada data counterparty yang cocok dengan kriteria pencarian/filter.</strong>
                </td>
            </tr>
        `;
    } else {
        pageRecords.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="mono-cell" style="font-weight: 700; color: #0284c7; white-space: nowrap; padding: 1.15rem 1.25rem;">${r.col1 || '-'}</td>
                <td style="font-weight: 600; color: #0f172a; padding: 1.15rem 1.25rem;">${r.col2 || '-'}</td>
                <td style="color: #475569; font-size: 12px; white-space: nowrap; padding: 1.15rem 1.25rem;">
                    <span style="background: #f1f5f9; padding: 4px 8px; border-radius: 6px; border: 1px solid #e2e8f0;">${r.col3 || '-'}</span>
                </td>
                <td style="white-space: nowrap; padding: 1.15rem 1.25rem;">${getRatingBadge(r.col4, r.col5)}</td>
                <td class="mono-cell" style="font-weight: 700; color: #0f172a; white-space: nowrap; padding: 1.15rem 1.25rem;">${r.col5 || '-'}</td>
                <td style="white-space: nowrap; padding: 1.15rem 1.25rem;">${getInvestmentGradeBadge(r.col6)}</td>
                <td class="mono-cell" style="text-align: right; font-weight: 700; color: #059669; white-space: nowrap; padding: 1.15rem 1.25rem;">${r.col8 || '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Render Pagination Controls (10 data per halaman)
    if (paginationBar) {
        if (totalRecords === 0) {
            paginationBar.innerHTML = '';
            return;
        }

        let pagesHtml = '';
        for (let p = 1; p <= totalPages; p++) {
            if (p === cpCurrentPage) {
                pagesHtml += `<button class="cp-btn-page active" disabled>${p}</button>`;
            } else {
                pagesHtml += `<button class="cp-btn-page" onclick="goToCpPage(${p})">${p}</button>`;
            }
        }

        paginationBar.innerHTML = `
            <div>
                Menampilkan <strong>${startIdx + 1} - ${endIdx}</strong> dari total <strong>${totalRecords}</strong> data 
                (Halaman <strong>${cpCurrentPage}</strong> dari <strong>${totalPages}</strong>)
            </div>
            <div style="display: flex; gap: 0.35rem; align-items: center;">
                <button class="cp-btn-page" ${cpCurrentPage === 1 ? 'disabled' : ''} onclick="goToCpPage(${cpCurrentPage - 1})">&larr; Sebelumnya</button>
                ${pagesHtml}
                <button class="cp-btn-page" ${cpCurrentPage === totalPages ? 'disabled' : ''} onclick="goToCpPage(${cpCurrentPage + 1})">Selanjutnya &rarr;</button>
            </div>
        `;
    }
}

window.goToCpPage = function(page) {
    cpCurrentPage = page;
    renderCpTablePage();
};

// Event Listeners untuk Search & Filter Modul Ahmad
document.addEventListener('DOMContentLoaded', () => {
    const cpSearch = document.getElementById('cpSearchInput');
    const cpCat = document.getElementById('cpCategoryFilter');

    if (cpSearch) {
        cpSearch.addEventListener('input', () => {
            cpCurrentPage = 1;
            filterAndRenderCpTable();
        });
    }

    if (cpCat) {
        cpCat.addEventListener('change', () => {
            cpCurrentPage = 1;
            filterAndRenderCpTable();
        });
    }
});


// Action Handler Harmonisasi EOM (Ahmad)
window.triggerHarmonize = async function() {
    const btn = document.getElementById('btnHarmonize');
    const btnText = document.getElementById('btnText');
    const cutOff = document.getElementById('cutOffDate')?.value || "2026-10-31";

    if (!confirm(`Jalankan penarikan data Antasena & harmonisasi rating EOM (Cut-off: ${cutOff})?\n\nProses ini akan mengonsolidasikan data dan menyegarkan tabel dim_counterparty_harmonized.`)) {
        return;
    }

    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = "Sedang Memproses Harmonisasi...";

    try {
        const response = await fetch("/master-counterparty/harmonize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cut_off: cutOff })
        });
        const result = await response.json();
        if (result.success) {
            alert(result.message || "Harmonisasi rating EOM berhasil dieksekusi!");
            window.location.reload();
        } else {
            alert("Gagal: " + (result.message || "Terjadi kesalahan"));
        }
    } catch (e) {
        alert("Gagal terhubung ke server: " + e.message);
    } finally {
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = "Tarik Data Antasena & Harmonisasi Rating";
    }
};
