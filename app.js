// ============================================================
// 배당금 시뮬레이터 - 메인 애플리케이션
// ============================================================

(function () {
    'use strict';

    // --- Data Store (localStorage) ---
    const STORAGE_KEYS = {
        holdings: 'divSim_holdings',
        dividends: 'divSim_dividends',
    };

    function loadData(key) {
        try {
            return JSON.parse(localStorage.getItem(key)) || [];
        } catch {
            return [];
        }
    }

    function saveData(key, data) {
        localStorage.setItem(key, JSON.stringify(data));
    }

    function generateId() {
        return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    }

    // --- State ---
    let holdings = loadData(STORAGE_KEYS.holdings);
    let dividends = loadData(STORAGE_KEYS.dividends);
    let charts = {};

    // --- Formatting ---
    function formatKRW(amount) {
        if (Math.abs(amount) >= 1e8) {
            return '₩' + (amount / 1e8).toFixed(2) + '억';
        }
        if (Math.abs(amount) >= 1e4) {
            return '₩' + (amount / 1e4).toFixed(1) + '만';
        }
        return '₩' + amount.toLocaleString('ko-KR', { maximumFractionDigits: 0 });
    }

    function formatPercent(value) {
        return (value * 100).toFixed(2) + '%';
    }

    function toKRW(amount, currency, exchangeRate) {
        return currency === 'USD' ? amount * exchangeRate : amount;
    }

    // --- Tab Navigation ---
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });

    // ============================================================
    // Portfolio Management
    // ============================================================
    const holdingForm = document.getElementById('holdingForm');
    const holdingIdField = document.getElementById('holdingId');
    const holdingSubmitBtn = document.getElementById('holdingSubmitBtn');
    const holdingCancelBtn = document.getElementById('holdingCancelBtn');

    holdingForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const data = {
            id: holdingIdField.value || generateId(),
            name: document.getElementById('stockName').value.trim(),
            ticker: document.getElementById('ticker').value.trim(),
            assetType: document.getElementById('assetType').value,
            sector: document.getElementById('sector').value || '기타',
            currency: document.getElementById('currency').value,
            shares: parseFloat(document.getElementById('shares').value),
            avgCost: parseFloat(document.getElementById('avgCost').value),
            currentPrice: parseFloat(document.getElementById('currentPrice').value),
            annualDividendPerShare: parseFloat(document.getElementById('annualDividendPerShare').value) || 0,
            exchangeRate: parseFloat(document.getElementById('exchangeRate').value) || 1350,
        };

        if (holdingIdField.value) {
            const idx = holdings.findIndex(h => h.id === data.id);
            if (idx !== -1) holdings[idx] = data;
        } else {
            holdings.push(data);
        }

        saveData(STORAGE_KEYS.holdings, holdings);
        holdingForm.reset();
        document.getElementById('exchangeRate').value = '1350';
        holdingIdField.value = '';
        holdingSubmitBtn.textContent = '추가';
        holdingCancelBtn.style.display = 'none';
        refreshAll();
    });

    holdingCancelBtn.addEventListener('click', () => {
        holdingForm.reset();
        document.getElementById('exchangeRate').value = '1350';
        holdingIdField.value = '';
        holdingSubmitBtn.textContent = '추가';
        holdingCancelBtn.style.display = 'none';
    });

    function editHolding(id) {
        const h = holdings.find(x => x.id === id);
        if (!h) return;
        holdingIdField.value = h.id;
        document.getElementById('stockName').value = h.name;
        document.getElementById('ticker').value = h.ticker || '';
        document.getElementById('assetType').value = h.assetType;
        document.getElementById('sector').value = h.sector;
        document.getElementById('currency').value = h.currency;
        document.getElementById('shares').value = h.shares;
        document.getElementById('avgCost').value = h.avgCost;
        document.getElementById('currentPrice').value = h.currentPrice;
        document.getElementById('annualDividendPerShare').value = h.annualDividendPerShare;
        document.getElementById('exchangeRate').value = h.exchangeRate;
        holdingSubmitBtn.textContent = '수정';
        holdingCancelBtn.style.display = 'inline-block';

        // Switch to portfolio tab
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelector('[data-tab="portfolio"]').classList.add('active');
        document.getElementById('portfolio').classList.add('active');
        holdingForm.scrollIntoView({ behavior: 'smooth' });
    }

    function deleteHolding(id) {
        if (!confirm('이 종목을 삭제하시겠습니까?')) return;
        holdings = holdings.filter(h => h.id !== id);
        saveData(STORAGE_KEYS.holdings, holdings);
        refreshAll();
    }

    function renderHoldingsTable() {
        const tbody = document.querySelector('#holdingsTable tbody');
        if (holdings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#999;padding:40px;">종목을 추가해주세요.</td></tr>';
            return;
        }

        tbody.innerHTML = holdings.map(h => {
            const costTotal = h.shares * h.avgCost;
            const currentTotal = h.shares * h.currentPrice;
            const returnPct = (currentTotal - costTotal) / costTotal;
            const yieldOnCost = h.avgCost > 0 ? h.annualDividendPerShare / h.avgCost : 0;
            const yieldOnCurrent = h.currentPrice > 0 ? h.annualDividendPerShare / h.currentPrice : 0;
            const currSymbol = h.currency === 'USD' ? '$' : '₩';

            return `<tr>
                <td><strong>${h.name}</strong>${h.ticker ? ` <small style="color:#999">(${h.ticker})</small>` : ''}</td>
                <td>${h.assetType}</td>
                <td>${h.shares.toLocaleString()}</td>
                <td>${currSymbol}${h.avgCost.toLocaleString()}</td>
                <td>${currSymbol}${h.currentPrice.toLocaleString()}</td>
                <td>${currSymbol}${costTotal.toLocaleString()}</td>
                <td>${currSymbol}${currentTotal.toLocaleString()}</td>
                <td class="${returnPct >= 0 ? 'positive' : 'negative'}">${formatPercent(returnPct)}</td>
                <td>${formatPercent(yieldOnCost)}</td>
                <td>${formatPercent(yieldOnCurrent)}</td>
                <td>
                    <button class="btn btn-edit" onclick="window._editHolding('${h.id}')">수정</button>
                    <button class="btn btn-danger" onclick="window._deleteHolding('${h.id}')">삭제</button>
                </td>
            </tr>`;
        }).join('');
    }

    window._editHolding = editHolding;
    window._deleteHolding = deleteHolding;

    // ============================================================
    // Dividend Records
    // ============================================================
    const dividendForm = document.getElementById('dividendForm');

    dividendForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const holdingId = document.getElementById('divHolding').value;
        const holding = holdings.find(h => h.id === holdingId);
        if (!holding) return alert('종목을 선택하세요.');

        const record = {
            id: generateId(),
            holdingId,
            holdingName: holding.name,
            assetType: holding.assetType,
            currency: holding.currency,
            exchangeRate: holding.exchangeRate,
            date: document.getElementById('divDate').value,
            amount: parseFloat(document.getElementById('divAmount').value),
            tax: parseFloat(document.getElementById('divTax').value) || 0,
        };

        dividends.push(record);
        dividends.sort((a, b) => b.date.localeCompare(a.date));
        saveData(STORAGE_KEYS.dividends, dividends);
        dividendForm.reset();
        refreshAll();
    });

    function deleteDividend(id) {
        if (!confirm('이 배당 기록을 삭제하시겠습니까?')) return;
        dividends = dividends.filter(d => d.id !== id);
        saveData(STORAGE_KEYS.dividends, dividends);
        refreshAll();
    }
    window._deleteDividend = deleteDividend;

    function populateHoldingSelects() {
        const selects = [
            document.getElementById('divHolding'),
            document.getElementById('divFilterHolding'),
            document.getElementById('analysisHolding'),
        ];
        selects.forEach(sel => {
            const currentVal = sel.value;
            const firstOption = sel.options[0].outerHTML;
            sel.innerHTML = firstOption + holdings.map(h =>
                `<option value="${h.id}">${h.name} (${h.assetType})</option>`
            ).join('');
            sel.value = currentVal;
        });
    }

    function populateYearFilter() {
        const sel = document.getElementById('divFilterYear');
        const years = [...new Set(dividends.map(d => d.date.slice(0, 4)))].sort().reverse();
        const currentVal = sel.value;
        sel.innerHTML = '<option value="">전체</option>' + years.map(y =>
            `<option value="${y}">${y}년</option>`
        ).join('');
        sel.value = currentVal;
    }

    document.getElementById('divFilterYear').addEventListener('change', renderDividendHistory);
    document.getElementById('divFilterHolding').addEventListener('change', renderDividendHistory);

    function renderDividendHistory() {
        const yearFilter = document.getElementById('divFilterYear').value;
        const holdingFilter = document.getElementById('divFilterHolding').value;
        const tbody = document.querySelector('#dividendHistoryTable tbody');

        let filtered = dividends;
        if (yearFilter) filtered = filtered.filter(d => d.date.startsWith(yearFilter));
        if (holdingFilter) filtered = filtered.filter(d => d.holdingId === holdingFilter);

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;padding:40px;">배당금 기록이 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = filtered.map(d => {
            const net = d.amount - d.tax;
            const amountKRW = toKRW(d.amount, d.currency, d.exchangeRate);
            const taxKRW = toKRW(d.tax, d.currency, d.exchangeRate);
            const netKRW = toKRW(net, d.currency, d.exchangeRate);
            return `<tr>
                <td>${d.date}</td>
                <td>${d.holdingName}</td>
                <td>${d.assetType}</td>
                <td>${formatKRW(amountKRW)}</td>
                <td>${formatKRW(taxKRW)}</td>
                <td>${formatKRW(netKRW)}</td>
                <td><button class="btn btn-danger" onclick="window._deleteDividend('${d.id}')">삭제</button></td>
            </tr>`;
        }).join('');
    }

    // ============================================================
    // Dashboard Calculations
    // ============================================================
    function calcDashboard() {
        let totalCostKRW = 0;
        let totalCurrentKRW = 0;
        let totalAnnualDivKRW = 0;

        holdings.forEach(h => {
            const cost = h.shares * h.avgCost;
            const current = h.shares * h.currentPrice;
            const annualDiv = h.shares * h.annualDividendPerShare;
            totalCostKRW += toKRW(cost, h.currency, h.exchangeRate);
            totalCurrentKRW += toKRW(current, h.currency, h.exchangeRate);
            totalAnnualDivKRW += toKRW(annualDiv, h.currency, h.exchangeRate);
        });

        const yieldOnCost = totalCostKRW > 0 ? totalAnnualDivKRW / totalCostKRW : 0;
        const yieldOnCurrent = totalCurrentKRW > 0 ? totalAnnualDivKRW / totalCurrentKRW : 0;

        // Yearly dividends from records
        const yearlyDivs = getYearlyDividends();
        const years = Object.keys(yearlyDivs).sort();
        let growthRate = 0;
        if (years.length >= 2) {
            const last = yearlyDivs[years[years.length - 1]];
            const prev = yearlyDivs[years[years.length - 2]];
            growthRate = prev > 0 ? (last - prev) / prev : 0;
        }

        document.getElementById('totalCost').textContent = formatKRW(totalCostKRW);
        document.getElementById('totalCurrentValue').textContent = formatKRW(totalCurrentKRW);
        document.getElementById('totalYieldOnCost').textContent = formatPercent(yieldOnCost);
        document.getElementById('totalYieldOnCurrent').textContent = formatPercent(yieldOnCurrent);
        document.getElementById('totalAnnualDividend').textContent = formatKRW(totalAnnualDivKRW);

        const growthEl = document.getElementById('dividendGrowthRate');
        growthEl.textContent = years.length >= 2 ? formatPercent(growthRate) : '-';
        growthEl.className = 'value ' + (growthRate >= 0 ? 'positive' : 'negative');

        return { totalCostKRW, totalCurrentKRW, totalAnnualDivKRW, yearlyDivs };
    }

    function getYearlyDividends() {
        const yearly = {};
        dividends.forEach(d => {
            const year = d.date.slice(0, 4);
            const amountKRW = toKRW(d.amount, d.currency, d.exchangeRate);
            yearly[year] = (yearly[year] || 0) + amountKRW;
        });
        return yearly;
    }

    function getYearlyDividendsByHolding() {
        const result = {};
        dividends.forEach(d => {
            const year = d.date.slice(0, 4);
            const key = d.holdingId;
            if (!result[key]) result[key] = {};
            const amountKRW = toKRW(d.amount, d.currency, d.exchangeRate);
            result[key][year] = (result[key][year] || 0) + amountKRW;
        });
        return result;
    }

    function getYearlyDividendsBySector() {
        const result = {};
        dividends.forEach(d => {
            const year = d.date.slice(0, 4);
            const holding = holdings.find(h => h.id === d.holdingId);
            const sector = holding ? holding.sector : '기타';
            if (!result[sector]) result[sector] = {};
            const amountKRW = toKRW(d.amount, d.currency, d.exchangeRate);
            result[sector][year] = (result[sector][year] || 0) + amountKRW;
        });
        return result;
    }

    // ============================================================
    // Weight Table
    // ============================================================
    function renderWeightTable(totalCostKRW) {
        const tbody = document.querySelector('#weightTable tbody');
        if (holdings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;padding:40px;">종목을 추가해주세요.</td></tr>';
            return;
        }

        tbody.innerHTML = holdings.map(h => {
            const costKRW = toKRW(h.shares * h.avgCost, h.currency, h.exchangeRate);
            const weight = totalCostKRW > 0 ? costKRW / totalCostKRW : 0;
            const yieldOnCost = h.avgCost > 0 ? h.annualDividendPerShare / h.avgCost : 0;
            const yieldOnCurrent = h.currentPrice > 0 ? h.annualDividendPerShare / h.currentPrice : 0;
            const annualDivKRW = toKRW(h.shares * h.annualDividendPerShare, h.currency, h.exchangeRate);

            return `<tr>
                <td><strong>${h.name}</strong></td>
                <td>${h.assetType}</td>
                <td>${h.sector}</td>
                <td>${formatKRW(costKRW)}</td>
                <td>${(weight * 100).toFixed(2)}%</td>
                <td>${formatPercent(yieldOnCost)}</td>
                <td>${formatPercent(yieldOnCurrent)}</td>
                <td>${formatKRW(annualDivKRW)}</td>
            </tr>`;
        }).join('');
    }

    // ============================================================
    // Charts
    // ============================================================
    const COLORS = [
        '#2563eb', '#16a34a', '#dc2626', '#f59e0b', '#8b5cf6',
        '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
        '#14b8a6', '#e11d48', '#a855f7', '#0ea5e9', '#eab308',
    ];

    function destroyChart(key) {
        if (charts[key]) {
            charts[key].destroy();
            charts[key] = null;
        }
    }

    function renderYearlyDividendChart(yearlyDivs) {
        destroyChart('yearlyDiv');
        const years = Object.keys(yearlyDivs).sort();
        if (years.length === 0) return;

        charts.yearlyDiv = new Chart(document.getElementById('yearlyDividendChart'), {
            type: 'bar',
            data: {
                labels: years.map(y => y + '년'),
                datasets: [{
                    label: '배당금 총액 (₩)',
                    data: years.map(y => Math.round(yearlyDivs[y])),
                    backgroundColor: '#2563eb',
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => formatKRW(ctx.raw)
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { callback: v => formatKRW(v) }
                    }
                }
            }
        });
    }

    function renderYearlyYieldChart(yearlyDivs) {
        destroyChart('yearlyYield');
        const years = Object.keys(yearlyDivs).sort();
        if (years.length === 0) return;

        // Use total cost at current state as approximation
        let totalCostKRW = 0;
        holdings.forEach(h => {
            totalCostKRW += toKRW(h.shares * h.avgCost, h.currency, h.exchangeRate);
        });

        charts.yearlyYield = new Chart(document.getElementById('yearlyYieldChart'), {
            type: 'line',
            data: {
                labels: years.map(y => y + '년'),
                datasets: [{
                    label: '배당수익률',
                    data: years.map(y => totalCostKRW > 0 ? (yearlyDivs[y] / totalCostKRW * 100) : 0),
                    borderColor: '#16a34a',
                    backgroundColor: 'rgba(22, 163, 74, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 5,
                    pointBackgroundColor: '#16a34a',
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.raw.toFixed(2) + '%'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { callback: v => v.toFixed(1) + '%' }
                    }
                }
            }
        });
    }

    function renderYearlyGrowthChart(yearlyDivs) {
        destroyChart('yearlyGrowth');
        const years = Object.keys(yearlyDivs).sort();
        if (years.length < 2) return;

        const growthYears = years.slice(1);
        const growthRates = growthYears.map((y, i) => {
            const prev = yearlyDivs[years[i]];
            const curr = yearlyDivs[y];
            return prev > 0 ? ((curr - prev) / prev * 100) : 0;
        });

        charts.yearlyGrowth = new Chart(document.getElementById('yearlyGrowthChart'), {
            type: 'bar',
            data: {
                labels: growthYears.map(y => y + '년'),
                datasets: [{
                    label: '배당 성장률',
                    data: growthRates,
                    backgroundColor: growthRates.map(v => v >= 0 ? '#16a34a' : '#dc2626'),
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.raw.toFixed(2) + '%'
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: { callback: v => v.toFixed(1) + '%' }
                    }
                }
            }
        });
    }

    function renderPortfolioWeightChart(totalCostKRW) {
        destroyChart('portfolioWeight');
        if (holdings.length === 0) return;

        const data = holdings.map(h => ({
            name: h.name,
            cost: toKRW(h.shares * h.avgCost, h.currency, h.exchangeRate),
        }));

        charts.portfolioWeight = new Chart(document.getElementById('portfolioWeightChart'), {
            type: 'doughnut',
            data: {
                labels: data.map(d => d.name),
                datasets: [{
                    data: data.map(d => Math.round(d.cost)),
                    backgroundColor: COLORS.slice(0, data.length),
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 14 } },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const pct = totalCostKRW > 0 ? (ctx.raw / totalCostKRW * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${formatKRW(ctx.raw)} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    function renderAssetTypeDividendChart() {
        destroyChart('assetTypeDiv');
        if (holdings.length === 0) return;

        const byType = {};
        holdings.forEach(h => {
            const divKRW = toKRW(h.shares * h.annualDividendPerShare, h.currency, h.exchangeRate);
            byType[h.assetType] = (byType[h.assetType] || 0) + divKRW;
        });

        const labels = Object.keys(byType);
        const values = labels.map(l => Math.round(byType[l]));

        charts.assetTypeDiv = new Chart(document.getElementById('assetTypeDividendChart'), {
            type: 'pie',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: ['#2563eb', '#f59e0b', '#dc2626', '#16a34a', '#8b5cf6'],
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 14 } },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const total = values.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${formatKRW(ctx.raw)} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    function renderSectorGrowthChart() {
        destroyChart('sectorGrowth');
        const bySector = getYearlyDividendsBySector();
        const sectors = Object.keys(bySector);
        if (sectors.length === 0) return;

        const allYears = [...new Set(dividends.map(d => d.date.slice(0, 4)))].sort();
        if (allYears.length < 2) return;

        const lastTwo = allYears.slice(-2);
        const growthData = sectors.map(sector => {
            const prev = bySector[sector][lastTwo[0]] || 0;
            const curr = bySector[sector][lastTwo[1]] || 0;
            return { sector, growth: prev > 0 ? ((curr - prev) / prev * 100) : (curr > 0 ? 100 : 0) };
        }).filter(d => d.growth !== 0);

        if (growthData.length === 0) return;

        charts.sectorGrowth = new Chart(document.getElementById('sectorGrowthChart'), {
            type: 'bar',
            data: {
                labels: growthData.map(d => d.sector),
                datasets: [{
                    label: `${lastTwo[0]}→${lastTwo[1]} 성장률`,
                    data: growthData.map(d => d.growth),
                    backgroundColor: growthData.map(d => d.growth >= 0 ? '#16a34a' : '#dc2626'),
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                indexAxis: 'y',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.raw.toFixed(2) + '%'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { callback: v => v.toFixed(0) + '%' }
                    }
                }
            }
        });
    }

    // ============================================================
    // Analysis Tab (Per-holding)
    // ============================================================
    document.getElementById('analysisHolding').addEventListener('change', renderAnalysis);

    function renderAnalysis() {
        const holdingId = document.getElementById('analysisHolding').value;
        const content = document.getElementById('analysisContent');

        if (!holdingId) {
            content.style.display = 'none';
            return;
        }
        content.style.display = 'block';

        const holding = holdings.find(h => h.id === holdingId);
        if (!holding) return;

        const holdingDivs = dividends.filter(d => d.holdingId === holdingId);
        const totalDiv = holdingDivs.reduce((s, d) => s + toKRW(d.amount, d.currency, d.exchangeRate), 0);
        const costKRW = toKRW(holding.shares * holding.avgCost, holding.currency, holding.exchangeRate);
        const currentKRW = toKRW(holding.shares * holding.currentPrice, holding.currency, holding.exchangeRate);
        const yoc = holding.avgCost > 0 ? holding.annualDividendPerShare / holding.avgCost : 0;
        const currentYield = holding.currentPrice > 0 ? holding.annualDividendPerShare / holding.currentPrice : 0;

        document.getElementById('analysisTotalDiv').textContent = formatKRW(totalDiv);
        document.getElementById('analysisYOC').textContent = formatPercent(yoc);
        document.getElementById('analysisCurrentYield').textContent = formatPercent(currentYield);

        // Yearly data for this holding
        const yearly = {};
        holdingDivs.forEach(d => {
            const year = d.date.slice(0, 4);
            yearly[year] = (yearly[year] || 0) + toKRW(d.amount, d.currency, d.exchangeRate);
        });

        const years = Object.keys(yearly).sort();
        let latestGrowth = 0;
        if (years.length >= 2) {
            const last = yearly[years[years.length - 1]];
            const prev = yearly[years[years.length - 2]];
            latestGrowth = prev > 0 ? (last - prev) / prev : 0;
        }

        const growthEl = document.getElementById('analysisGrowth');
        growthEl.textContent = years.length >= 2 ? formatPercent(latestGrowth) : '-';
        growthEl.className = 'value ' + (latestGrowth >= 0 ? 'positive' : 'negative');

        // Yearly chart
        destroyChart('analysisYearly');
        if (years.length > 0) {
            charts.analysisYearly = new Chart(document.getElementById('analysisYearlyChart'), {
                type: 'bar',
                data: {
                    labels: years.map(y => y + '년'),
                    datasets: [{
                        label: '배당금',
                        data: years.map(y => Math.round(yearly[y])),
                        backgroundColor: '#2563eb',
                        borderRadius: 6,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: ctx => formatKRW(ctx.raw) } }
                    },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: v => formatKRW(v) } }
                    }
                }
            });
        }

        // Growth chart
        destroyChart('analysisGrowth');
        if (years.length >= 2) {
            const growthYears = years.slice(1);
            const rates = growthYears.map((y, i) => {
                const prev = yearly[years[i]];
                return prev > 0 ? ((yearly[y] - prev) / prev * 100) : 0;
            });

            charts.analysisGrowth = new Chart(document.getElementById('analysisGrowthChart'), {
                type: 'line',
                data: {
                    labels: growthYears.map(y => y + '년'),
                    datasets: [{
                        label: '성장률',
                        data: rates,
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 5,
                        pointBackgroundColor: '#8b5cf6',
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: ctx => ctx.raw.toFixed(2) + '%' } }
                    },
                    scales: {
                        y: { ticks: { callback: v => v.toFixed(1) + '%' } }
                    }
                }
            });
        }

        // History table
        const tbody = document.querySelector('#analysisHistoryTable tbody');
        if (holdingDivs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#999;padding:40px;">배당 기록이 없습니다.</td></tr>';
        } else {
            tbody.innerHTML = holdingDivs.sort((a, b) => b.date.localeCompare(a.date)).map(d => {
                const amtKRW = toKRW(d.amount, d.currency, d.exchangeRate);
                const taxKRW = toKRW(d.tax, d.currency, d.exchangeRate);
                return `<tr>
                    <td>${d.date}</td>
                    <td>${formatKRW(amtKRW)}</td>
                    <td>${formatKRW(taxKRW)}</td>
                    <td>${formatKRW(amtKRW - taxKRW)}</td>
                </tr>`;
            }).join('');
        }
    }

    // ============================================================
    // Refresh All
    // ============================================================
    function refreshAll() {
        populateHoldingSelects();
        populateYearFilter();
        renderHoldingsTable();
        renderDividendHistory();

        const { totalCostKRW, yearlyDivs } = calcDashboard();
        renderWeightTable(totalCostKRW);
        renderYearlyDividendChart(yearlyDivs);
        renderYearlyYieldChart(yearlyDivs);
        renderYearlyGrowthChart(yearlyDivs);
        renderPortfolioWeightChart(totalCostKRW);
        renderAssetTypeDividendChart();
        renderSectorGrowthChart();

        if (document.getElementById('analysisHolding').value) {
            renderAnalysis();
        }
    }

    // --- Initial Load ---
    refreshAll();
})();
