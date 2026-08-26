(function () {
  'use strict';

  const pageData = window.CITY_PAGE_DATA;
  if (!pageData) return;

  function parseLocalDate(isoDate) {
    const parts = isoDate.split('-').map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function formatMonthYear(isoDate) {
    return parseLocalDate(isoDate).toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric'
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatPrice(price) {
    if (price === null || price === undefined) return 'N/A';
    return '$' + Number(price).toLocaleString('en-US', { maximumFractionDigits: 0 });
  }

  function formatAppreciation(totalReturn, cagr) {
    if (totalReturn === null || cagr === null || totalReturn === undefined || cagr === undefined) {
      return 'N/A';
    }
    const sign = totalReturn >= 0 ? '+' : '';
    const cagrSign = cagr >= 0 ? '+' : '';
    const className = totalReturn >= 0 ? 'positive' : 'negative';
    return '<span class="' + className + '">' + sign + totalReturn.toFixed(2) +
      '%<span class="cagr">(' + cagrSign + cagr.toFixed(2) + '%)</span></span>';
  }

  function initChart() {
    const canvas = document.querySelector('.sf-stats-section canvas');
    const chart = pageData.chart;
    if (!canvas || !chart || !window.Chart || !chart.dates.length || !chart.prices.length) return;

    const finitePrices = chart.prices.filter(Number.isFinite);
    if (!finitePrices.length) return;
    const suggestedMin = Math.floor((Math.min.apply(null, finitePrices) * 0.85) / 10000) * 10000;

    new window.Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: chart.dates,
        datasets: [{
          label: 'Price Index',
          data: chart.prices,
          borderColor: '#2c5364',
          backgroundColor: 'rgba(44, 83, 100, 0.10)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: '#d4a853',
          pointHoverBorderColor: '#fff',
          pointHoverBorderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (context) {
                return formatMonthYear(chart.dates[context[0].dataIndex]);
              },
              label: function (context) {
                return 'Price Index: ' + formatPrice(context.parsed.y);
              }
            },
            backgroundColor: 'rgba(0,0,0,0.82)',
            padding: 12,
            titleFont: { size: 14, weight: 'bold' },
            bodyFont: { size: 13 }
          }
        },
        scales: {
          x: {
            ticks: {
              maxRotation: 45,
              minRotation: 45,
              autoSkip: false,
              callback: function (_value, index) {
                const date = parseLocalDate(chart.dates[index]);
                if (index === chart.dates.length - 1) return formatMonthYear(chart.dates[index]);
                if (date.getMonth() === 0 && date.getFullYear() % 2 === 0) {
                  return 'Jan ' + date.getFullYear();
                }
                return '';
              },
              font: { size: 10 }
            },
            grid: { display: false }
          },
          y: {
            suggestedMin: suggestedMin,
            ticks: {
              callback: function (value) {
                if (value >= 1000000) return '$' + (value / 1000000).toFixed(1) + 'M';
                return '$' + (value / 1000).toFixed(0) + 'K';
              },
              font: { size: 11 }
            },
            grid: { color: 'rgba(0,0,0,0.05)' }
          }
        }
      }
    });
  }

  function initTable() {
    const tableBody = document.getElementById('tableBody');
    const table = document.getElementById('dataTable');
    const tableContainer = document.getElementById('bayarea-appreciation-table');
    const originalHeader = document.getElementById('originalHeader');
    const stickyHeader = document.getElementById('stickyHeader');
    if (!tableBody || !table || !tableContainer || !originalHeader || !stickyHeader) return;

    let currentSort = { column: null, direction: 'asc' };
    const rows = pageData.neighborhoods.slice();

    function renderTable(sortedRows) {
      tableBody.innerHTML = '';
      sortedRows.forEach(function (row) {
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td class="city-name">(#' + row.rank + ') ' + escapeHtml(row.name) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_1y, row.cagr_1y) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_3y, row.cagr_3y) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_5y, row.cagr_5y) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_10y, row.cagr_10y) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_20y, row.cagr_20y) + '</td>' +
          '<td class="number">' + formatAppreciation(row.total_return_25y, row.cagr_25y) + '</td>' +
          '<td class="price">' + formatPrice(row.typical_price) + '</td>';
        tableBody.appendChild(tr);
      });
    }

    function syncColumnWidths() {
      const originalHeaders = originalHeader.querySelectorAll('th');
      const stickyHeaders = stickyHeader.querySelectorAll('th');
      originalHeaders.forEach(function (th, index) {
        const width = th.offsetWidth;
        if (!stickyHeaders[index]) return;
        stickyHeaders[index].style.width = width + 'px';
        stickyHeaders[index].style.minWidth = width + 'px';
        stickyHeaders[index].style.maxWidth = width + 'px';
      });
      const tableRect = table.getBoundingClientRect();
      stickyHeader.style.width = tableRect.width + 'px';
      stickyHeader.style.left = tableRect.left + 'px';
    }

    function updateSortIndicators(column, direction) {
      document.querySelectorAll('#bayarea-appreciation-table th').forEach(function (th) {
        th.classList.remove('sort-asc', 'sort-desc');
      });
      document.querySelectorAll('#bayarea-appreciation-table th[data-column="' + column + '"]').forEach(function (th) {
        th.classList.add('sort-' + direction);
      });
    }

    function sortData(column) {
      let direction = 'asc';
      if (currentSort.column === column) direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
      const sorted = rows.slice().sort(function (a, b) {
        const aValue = a[column];
        const bValue = b[column];
        if (aValue === null && bValue === null) return 0;
        if (aValue === null) return 1;
        if (bValue === null) return -1;
        if (column === 'city' || column === 'rank') {
          return direction === 'asc' ? a.rank - b.rank : b.rank - a.rank;
        }
        if (column === 'name') return direction === 'asc' ? aValue.localeCompare(bValue) : bValue.localeCompare(aValue);
        return direction === 'asc' ? aValue - bValue : bValue - aValue;
      });
      currentSort = { column: column, direction: direction };
      updateSortIndicators(column, direction);
      renderTable(sorted);
    }

    function handleStickyHeader() {
      if (originalHeader.getBoundingClientRect().top < 0) {
        stickyHeader.classList.add('visible');
        syncColumnWidths();
      } else {
        stickyHeader.classList.remove('visible');
      }
    }

    renderTable(rows);
    document.querySelectorAll('#bayarea-appreciation-table th.sortable').forEach(function (th) {
      th.addEventListener('click', function () { sortData(th.dataset.column); });
    });
    window.addEventListener('scroll', handleStickyHeader, { passive: true });
    window.addEventListener('resize', syncColumnWidths);
    window.addEventListener('orientationchange', syncColumnWidths);
    tableContainer.addEventListener('scroll', syncColumnWidths, { passive: true });
    syncColumnWidths();
    handleStickyHeader();
  }

  function init() {
    initChart();
    initTable();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
