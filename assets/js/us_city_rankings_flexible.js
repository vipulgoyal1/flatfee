(function() {
    const metroData = window.US_METRO_CITY_DATA || {};
    const allRows = [];
    const stateSet = new Set();
    const countyMap = new Map();
    const metroSet = new Set();

    // Approximate mapping: Zillow size rank -> Census 2023 incorporated-place population level.
    const populationToMaxSizeRank = {
        10000: 3179,
        20000: 1894,
        30000: 1329,
        50000: 801,
        75000: 499,
        100000: 333,
        150000: 179,
        200000: 124,
        300000: 69,
        500000: 38,
        1000000: 9
    };

    Object.entries(metroData).forEach(([metro, rows]) => {
        (rows || []).forEach((row) => {
            if (!row || !row.city || !row.state) return;

            const normalized = {
                metro,
                city: row.city,
                county: row.county || "",
                state: row.state,
                sizeRank: Number(row.sizeRank),
                typical_price: row.typical_price == null ? null : Number(row.typical_price),
                total_return_1y: row.total_return_1y == null ? null : Number(row.total_return_1y),
                total_return_3y: row.total_return_3y == null ? null : Number(row.total_return_3y),
                total_return_5y: row.total_return_5y == null ? null : Number(row.total_return_5y),
                total_return_10y: row.total_return_10y == null ? null : Number(row.total_return_10y),
                total_return_20y: row.total_return_20y == null ? null : Number(row.total_return_20y),
                total_return_25y: row.total_return_25y == null ? null : Number(row.total_return_25y),
                cagr_1y: row.cagr_1y == null ? null : Number(row.cagr_1y),
                cagr_3y: row.cagr_3y == null ? null : Number(row.cagr_3y),
                cagr_5y: row.cagr_5y == null ? null : Number(row.cagr_5y),
                cagr_10y: row.cagr_10y == null ? null : Number(row.cagr_10y),
                cagr_20y: row.cagr_20y == null ? null : Number(row.cagr_20y),
                cagr_25y: row.cagr_25y == null ? null : Number(row.cagr_25y)
            };

            // Exclude rows without 10-year return data.
            if (normalized.total_return_10y == null || Number.isNaN(normalized.total_return_10y)) return;

            allRows.push(normalized);
            stateSet.add(normalized.state);
            metroSet.add(metro);
            if (normalized.county) {
                const countyKey = `${normalized.county}||${normalized.state}`;
                countyMap.set(countyKey, `${normalized.county} (${normalized.state})`);
            }
        });
    });

    const stateOptions = [...stateSet].sort((a, b) => a.localeCompare(b)).map((value) => ({ value, label: value, search: value.toLowerCase() }));
    const countyOptions = [...countyMap.entries()]
        .map(([value, label]) => ({ value, label, search: label.toLowerCase() }))
        .sort((a, b) => a.label.localeCompare(b.label));
    const metroOptions = [...metroSet].sort((a, b) => a.localeCompare(b)).map((value) => ({ value, label: value, search: value.toLowerCase() }));

    const optionsByType = {
        state: stateOptions,
        county: countyOptions,
        metro: metroOptions
    };

    const selectedValues = {
        state: new Set(),
        county: new Set(),
        metro: new Set()
    };

    const tableBody = document.getElementById("tableBody");
    const heading = document.getElementById("selectedMetroHeading");
    const status = document.getElementById("metroSelectionStatus");

    const combineMode = document.getElementById("combineMode");
    const minPopulation = document.getElementById("minPopulation");
    const rowLimit = document.getElementById("rowLimit");

    const applyButton = document.getElementById("applySelectionButton");
    const resetButton = document.getElementById("resetSelectionButton");

    const tokenUI = {
        state: {
            input: document.getElementById("stateInput"),
            chips: document.getElementById("stateChips"),
            suggestions: document.getElementById("stateSuggestions"),
            selectAll: document.getElementById("stateSelectVisible"),
            clear: document.getElementById("stateClear")
        },
        county: {
            input: document.getElementById("countyInput"),
            chips: document.getElementById("countyChips"),
            suggestions: document.getElementById("countySuggestions"),
            selectAll: document.getElementById("countySelectVisible"),
            clear: document.getElementById("countyClear")
        },
        metro: {
            input: document.getElementById("metroInput"),
            chips: document.getElementById("metroChips"),
            suggestions: document.getElementById("metroSuggestions"),
            selectAll: document.getElementById("metroSelectVisible"),
            clear: document.getElementById("metroClear")
        }
    };

    let activeRows = [];
    let currentSort = { column: null, direction: "asc" };

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatPrice(price) {
        if (price == null || Number.isNaN(price)) return "N/A";
        return "$" + Number(price).toLocaleString();
    }

    function formatAppreciation(totalReturn, cagr) {
        if (totalReturn == null || cagr == null || Number.isNaN(totalReturn) || Number.isNaN(cagr)) return "N/A";
        const sign = totalReturn >= 0 ? "+" : "";
        const cagrSign = cagr >= 0 ? "+" : "";
        const className = totalReturn >= 0 ? "positive" : "negative";
        return `<span class="${className}">${sign}${totalReturn.toFixed(2)}%<span class="cagr">(${cagrSign}${cagr.toFixed(2)}%)</span></span>`;
    }

    function formatRowLabel(row) {
        const rankText = Number.isFinite(row.sizeRank) ? `#${row.sizeRank}` : "#N/A";
        return `(${rankText}) ${escapeHtml(row.city)}, ${escapeHtml(row.state)}`;
    }

    function getMetricValue(row, metric) {
        const value = row[metric];
        if (value == null || Number.isNaN(value)) return null;
        return Number(value);
    }

    function renderTable(rows) {
        if (!tableBody) return;
        tableBody.innerHTML = "";

        rows.forEach((row) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="city-name">${formatRowLabel(row)}</td>
                <td class="number">${formatAppreciation(row.total_return_1y, row.cagr_1y)}</td>
                <td class="number">${formatAppreciation(row.total_return_3y, row.cagr_3y)}</td>
                <td class="number">${formatAppreciation(row.total_return_5y, row.cagr_5y)}</td>
                <td class="number">${formatAppreciation(row.total_return_10y, row.cagr_10y)}</td>
                <td class="number">${formatAppreciation(row.total_return_20y, row.cagr_20y)}</td>
                <td class="number">${formatAppreciation(row.total_return_25y, row.cagr_25y)}</td>
                <td class="price">${formatPrice(row.typical_price)}</td>
            `;
            tableBody.appendChild(tr);
        });
    }

    function syncColumnWidths() {
        const originalHeaders = document.querySelectorAll("#originalHeader th");
        const stickyHeaders = document.querySelectorAll("#stickyHeader th");
        const table = document.getElementById("dataTable");
        const stickyHeader = document.getElementById("stickyHeader");

        if (!table || !stickyHeader) return;

        originalHeaders.forEach((th, index) => {
            const width = th.offsetWidth;
            if (stickyHeaders[index]) {
                stickyHeaders[index].style.width = width + "px";
                stickyHeaders[index].style.minWidth = width + "px";
                stickyHeaders[index].style.maxWidth = width + "px";
            }
        });

        const tableRect = table.getBoundingClientRect();
        stickyHeader.style.width = tableRect.width + "px";
        stickyHeader.style.left = tableRect.left + "px";
    }

    function updateSortIndicators(column, direction) {
        document.querySelectorAll("#bayarea-appreciation-table th").forEach((th) => {
            th.classList.remove("sort-asc", "sort-desc");
        });

        if (!column || !direction) return;

        [
            `#originalHeader th[data-column="${column}"]`,
            `#stickyHeader th[data-column="${column}"]`
        ].forEach((selector) => {
            const th = document.querySelector(selector);
            if (th) th.classList.add(`sort-${direction}`);
        });
    }

    function sortedRows(rows, column, direction) {
        return [...rows].sort((a, b) => {
            let aVal;
            let bVal;

            if (column === "city") {
                aVal = Number.isFinite(a.sizeRank) ? a.sizeRank : Number.MAX_SAFE_INTEGER;
                bVal = Number.isFinite(b.sizeRank) ? b.sizeRank : Number.MAX_SAFE_INTEGER;
            } else {
                aVal = a[column];
                bVal = b[column];
            }

            const aMissing = aVal == null || Number.isNaN(aVal);
            const bMissing = bVal == null || Number.isNaN(bVal);
            if (aMissing && bMissing) return 0;
            if (aMissing) return 1;
            if (bMissing) return -1;

            if (typeof aVal === "number" && typeof bVal === "number") {
                return direction === "asc" ? aVal - bVal : bVal - aVal;
            }

            const compare = String(aVal).localeCompare(String(bVal));
            return direction === "asc" ? compare : -compare;
        });
    }

    function sortData(column) {
        let direction = "asc";
        if (currentSort.column === column) {
            direction = currentSort.direction === "asc" ? "desc" : "asc";
        }

        currentSort = { column, direction };
        activeRows = sortedRows(activeRows, column, direction);
        updateSortIndicators(column, direction);
        renderTable(activeRows);
        syncColumnWidths();
    }

    function handleStickyHeader() {
        const originalHeader = document.getElementById("originalHeader");
        const stickyHeader = document.getElementById("stickyHeader");
        if (!originalHeader || !stickyHeader) return;

        const rect = originalHeader.getBoundingClientRect();
        if (rect.top < 0) {
            stickyHeader.classList.add("visible");
            syncColumnWidths();
        } else {
            stickyHeader.classList.remove("visible");
        }
    }

    function setStatus(message, isError) {
        if (!status) return;
        status.textContent = message;
        status.style.color = isError ? "#b42318" : "#4f5b67";
    }

    function getOptionLabel(type, value) {
        const option = optionsByType[type].find((item) => item.value === value);
        return option ? option.label : value;
    }

    function renderChips(type) {
        const ui = tokenUI[type];
        if (!ui || !ui.chips) return;

        const values = [...selectedValues[type]];

        if (values.length === 0) {
            ui.chips.innerHTML = "";
            return;
        }

        const maxVisible = 10;
        const visible = values.slice(0, maxVisible);
        const hiddenCount = values.length - visible.length;

        const html = visible.map((value) => {
            const label = escapeHtml(getOptionLabel(type, value));
            return `<span class="token-chip">${label}<button type="button" class="token-remove" data-type="${type}" data-value="${escapeHtml(value)}" aria-label="Remove">&times;</button></span>`;
        }).join("");

        ui.chips.innerHTML = html + (hiddenCount > 0 ? `<span class="token-chip more">+${hiddenCount} more</span>` : "");
    }

    function hideSuggestions(type) {
        const box = tokenUI[type] && tokenUI[type].suggestions;
        if (!box) return;
        box.classList.remove("visible");
        box.innerHTML = "";
    }

    function hideAllSuggestions() {
        hideSuggestions("state");
        hideSuggestions("county");
        hideSuggestions("metro");
    }

    function findMatches(type, query) {
        const q = (query || "").trim().toLowerCase();
        if (!q) return [];
        const selected = selectedValues[type];
        return optionsByType[type]
            .filter((option) => !selected.has(option.value) && option.search.includes(q))
            .slice(0, 12);
    }

    function renderSuggestions(type, query) {
        const ui = tokenUI[type];
        if (!ui || !ui.suggestions) return;

        const matches = findMatches(type, query);
        if (!matches.length) {
            hideSuggestions(type);
            return;
        }

        ui.suggestions.innerHTML = matches
            .map((match) => `<div class="suggestion-item" data-type="${type}" data-value="${escapeHtml(match.value)}">${escapeHtml(match.label)}</div>`)
            .join("");
        ui.suggestions.classList.add("visible");
    }

    function addSelection(type, value) {
        const set = selectedValues[type];
        if (!set || set.has(value)) return;
        set.add(value);
        renderChips(type);
    }

    function removeSelection(type, value) {
        const set = selectedValues[type];
        if (!set) return;
        set.delete(value);
        renderChips(type);
    }

    function selectAll(type) {
        const set = selectedValues[type];
        if (!set) return;
        set.clear();
        optionsByType[type].forEach((option) => set.add(option.value));
        renderChips(type);
    }

    function clearSelections(type) {
        const set = selectedValues[type];
        if (!set) return;
        set.clear();
        renderChips(type);
    }

    function commitInput(type) {
        const ui = tokenUI[type];
        if (!ui || !ui.input) return;

        const query = ui.input.value.trim();
        if (!query) return;

        const q = query.toLowerCase();
        const options = optionsByType[type].filter((opt) => !selectedValues[type].has(opt.value));
        let chosen = options.find((opt) => opt.label.toLowerCase() === q || opt.value.toLowerCase() === q) || null;
        if (!chosen) {
            const matches = options.filter((opt) => opt.search.includes(q));
            if (matches.length === 1) chosen = matches[0];
            else if (matches.length > 1) chosen = matches[0];
        }

        if (chosen) {
            addSelection(type, chosen.value);
            ui.input.value = "";
            hideSuggestions(type);
        } else {
            renderSuggestions(type, query);
        }
    }

    function selectedSummary() {
        const stateCount = selectedValues.state.size;
        const countyCount = selectedValues.county.size;
        const metroCount = selectedValues.metro.size;
        const minPop = minPopulation ? Number(minPopulation.value) : 500000;

        const stateText = stateCount === stateOptions.length ? "all states" : `${stateCount} state(s)`;
        const popText = minPop > 0 ? `min pop ${minPop.toLocaleString()}+` : "no min population";
        return `${stateText}, ${countyCount} county(s), ${metroCount} metro area(s), ${popText}`;
    }

    function filterRows() {
        const stateActive = selectedValues.state.size > 0;
        const countyActive = selectedValues.county.size > 0;
        const metroActive = selectedValues.metro.size > 0;
        const activeCount = (stateActive ? 1 : 0) + (countyActive ? 1 : 0) + (metroActive ? 1 : 0);
        const mode = combineMode ? combineMode.value : "any";
        const minPop = minPopulation ? Number(minPopulation.value) : 500000;
        const maxSizeRank = minPop > 0 ? (populationToMaxSizeRank[minPop] || Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;

        return allRows.filter((row) => {
            if (minPop > 0) {
                if (!Number.isFinite(row.sizeRank)) return false;
                if (row.sizeRank > maxSizeRank) return false;
            }

            const countyKey = `${row.county}||${row.state}`;
            const matches = {
                state: !stateActive || selectedValues.state.has(row.state),
                county: !countyActive || selectedValues.county.has(countyKey),
                metro: !metroActive || selectedValues.metro.has(row.metro)
            };

            if (activeCount === 0) return true;
            if (mode === "all") return matches.state && matches.county && matches.metro;
            return (stateActive && matches.state) || (countyActive && matches.county) || (metroActive && matches.metro);
        });
    }

    function applySelection() {
        const metric = "total_return_10y";
        const maxRows = rowLimit ? Number(rowLimit.value) : 250;
        const filtered = filterRows();

        const sortedByMetric = [...filtered].sort((a, b) => {
            const aVal = getMetricValue(a, metric);
            const bVal = getMetricValue(b, metric);
            if (aVal === null && bVal === null) return 0;
            if (aVal === null) return 1;
            if (bVal === null) return -1;
            return bVal - aVal;
        });

        activeRows = maxRows > 0 ? sortedByMetric.slice(0, maxRows) : sortedByMetric;
        currentSort = { column: metric, direction: "desc" };

        updateSortIndicators(metric, "desc");
        renderTable(activeRows);
        syncColumnWidths();
        handleStickyHeader();

        if (heading) heading.textContent = "US City Appreciation Rankings";

        if (!activeRows.length) {
            setStatus("No cities match the current selection. Adjust filters and try again.", true);
            return;
        }

        setStatus(
            `Showing ${activeRows.length.toLocaleString()} of ${filtered.length.toLocaleString()} matched cities, ranked by 10 year total return. Filters: ${selectedSummary()}.`,
            false
        );
    }

    function resetFilters() {
        selectedValues.state.clear();
        selectedValues.county.clear();
        selectedValues.metro.clear();
        stateOptions.forEach((opt) => selectedValues.state.add(opt.value));

        if (combineMode) combineMode.value = "any";
        if (minPopulation) minPopulation.value = "500000";
        if (rowLimit) rowLimit.value = "250";

        Object.keys(tokenUI).forEach((type) => {
            if (tokenUI[type].input) tokenUI[type].input.value = "";
            hideSuggestions(type);
            renderChips(type);
        });
    }

    function wireTypeahead(type) {
        const ui = tokenUI[type];
        if (!ui || !ui.input || !ui.suggestions) return;

        ui.input.addEventListener("input", () => {
            renderSuggestions(type, ui.input.value);
        });

        ui.input.addEventListener("focus", () => {
            if (ui.input.value.trim()) renderSuggestions(type, ui.input.value);
        });

        ui.input.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === "Tab" || event.key === ",") {
                event.preventDefault();
                commitInput(type);
            }
            if (event.key === "Backspace" && !ui.input.value.trim() && selectedValues[type].size > 0) {
                const last = [...selectedValues[type]].pop();
                removeSelection(type, last);
            }
        });
    }

    function wireTokenControls() {
        Object.keys(tokenUI).forEach((type) => {
            wireTypeahead(type);

            const ui = tokenUI[type];
            if (ui.selectAll) {
                ui.selectAll.addEventListener("click", () => {
                    selectAll(type);
                    if (ui.input) ui.input.value = "";
                    hideSuggestions(type);
                });
            }
            if (ui.clear) {
                ui.clear.addEventListener("click", () => {
                    clearSelections(type);
                    if (ui.input) ui.input.value = "";
                    hideSuggestions(type);
                });
            }

            if (ui.suggestions) {
                ui.suggestions.addEventListener("click", (event) => {
                    const item = event.target.closest(".suggestion-item");
                    if (!item) return;
                    const value = item.dataset.value;
                    addSelection(type, value);
                    if (ui.input) ui.input.value = "";
                    hideSuggestions(type);
                });
            }
        });

        document.addEventListener("click", (event) => {
            const removeBtn = event.target.closest(".token-remove");
            if (removeBtn) {
                const type = removeBtn.dataset.type;
                const value = removeBtn.dataset.value;
                removeSelection(type, value);
                return;
            }

            const insideTokenArea = event.target.closest(".filter-card");
            if (!insideTokenArea) hideAllSuggestions();
        });
    }

    function wireActionButtons() {
        if (applyButton) {
            applyButton.addEventListener("click", applySelection);
        }

        if (resetButton) {
            resetButton.addEventListener("click", () => {
                resetFilters();
                applySelection();
            });
        }
    }

    function initSortingHandlers() {
        document.querySelectorAll("#bayarea-appreciation-table th.sortable").forEach((th) => {
            th.addEventListener("click", () => {
                const column = th.dataset.column;
                sortData(column);
            });
        });
    }

    function initTable() {
        if (!tableBody) return;
        let syncRaf = null;
        const syncStickyIfVisible = () => {
            const stickyHeader = document.getElementById("stickyHeader");
            if (!stickyHeader || !stickyHeader.classList.contains("visible")) return;
            if (syncRaf !== null) cancelAnimationFrame(syncRaf);
            syncRaf = requestAnimationFrame(() => {
                syncColumnWidths();
                syncRaf = null;
            });
        };

        if (!allRows.length) {
            setStatus("City data is unavailable.", true);
            return;
        }

        // Default view: all states + 500k min population.
        stateOptions.forEach((opt) => selectedValues.state.add(opt.value));
        if (minPopulation) minPopulation.value = "500000";

        Object.keys(tokenUI).forEach((type) => renderChips(type));

        wireTokenControls();
        wireActionButtons();
        initSortingHandlers();

        window.addEventListener("scroll", handleStickyHeader);
        const tableContainer = document.getElementById("bayarea-appreciation-table");
        if (tableContainer) {
            tableContainer.addEventListener("scroll", syncStickyIfVisible, { passive: true });
        }
        window.addEventListener("resize", () => {
            syncStickyIfVisible();
        });
        window.addEventListener("orientationchange", syncStickyIfVisible);

        applySelection();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initTable);
    } else {
        initTable();
    }
})();
