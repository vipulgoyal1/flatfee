/* San Jose MLS charts v3. Uses reported values only. */
(function () {
  "use strict";

  if (!window.Chart || !window.SAN_JOSE_MLS_V3_DATA) return;

  var DATA = window.SAN_JOSE_MLS_V3_DATA;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var COLORS = {
    teal: "#2c5364",
    tealFill: "rgba(44,83,100,0.10)",
    gold: "#d4a853",
    goldFill: "rgba(212,168,83,0.68)",
    blueFill: "rgba(98,138,160,0.50)",
    redFill: "rgba(168,90,74,0.62)",
    grid: "rgba(0,0,0,0.055)"
  };

  var resolution = "yearly";
  var charts = [];

  var metricDefinitions = {
    salePrice: {
      canvas: "sjMlsV3SalePrice",
      snapshot: "sjMlsV3SnapshotSalePrice",
      change: "sjMlsV3ChangeSalePrice",
      title: "Median Sale Price",
      chartType: "line",
      axisTitle: "Sale price",
      format: money,
      tick: compactMoney,
      monthlyTooltip: "Median sale price",
      groupedTooltip: "Average monthly median",
      changeText: percentChange
    },
    salePriceChange: {
      canvas: "sjMlsV3SalePriceChange",
      title: "Year-over-Year Median Sale Price Change",
      chartType: "bar",
      axisTitle: "Change from one year earlier",
      format: function (number) { return signedNumber(number, 1) + "%"; },
      tick: function (number) { return signedNumber(number, 0) + "%"; },
      monthlyTooltip: "Year-over-year change",
      groupedTooltip: "Year-over-year change",
      sourceMetric: "salePrice",
      derived: "yearOverYear",
      referenceLine: 0
    },
    daysOnMarket: {
      canvas: "sjMlsV3DaysOnMarket",
      snapshot: "sjMlsV3SnapshotDaysOnMarket",
      change: "sjMlsV3ChangeDaysOnMarket",
      title: "Median Days on Market",
      chartType: "line",
      axisTitle: "Days to Sell",
      format: function (number) { return decimal(number, 1) + " days"; },
      snapshotFormat: function (number) { return decimal(number, 0) + " days"; },
      tick: function (number) { return decimal(number, 0); },
      monthlyTooltip: "Median days on market",
      groupedTooltip: "Average monthly median",
      changeText: function (current, prior) {
        return signedNumber(current - prior, 0) + " days year over year";
      }
    },
    saleToList: {
      canvas: "sjMlsV3SaleToList",
      snapshot: "sjMlsV3SnapshotSaleToList",
      change: "sjMlsV3ChangeSaleToList",
      title: "Sale-to-List Performance",
      chartType: "line",
      axisTitle: "Sale price as % of list price",
      format: function (number) { return decimal(number, 1) + "%"; },
      tick: function (number) { return decimal(number, 0) + "%"; },
      monthlyTooltip: "Sale-to-list performance",
      groupedTooltip: "Average monthly performance",
      changeText: function (current, prior) {
        return signedNumber(current - prior, 1) + " points year over year";
      },
      referenceLine: 100,
      referenceLabel: "100% of list price"
    },
    closedSales: {
      canvas: "sjMlsV3ClosedSales",
      snapshot: "sjMlsV3SnapshotClosedSales",
      change: "sjMlsV3ChangeClosedSales",
      title: "Closed-Sales Volume",
      chartType: "bar",
      axisTitle: "Closed sales",
      format: function (number) { return Math.round(number).toLocaleString("en-US") + " sales"; },
      tick: function (number) { return Math.round(number).toLocaleString("en-US"); },
      monthlyTooltip: "Closed sales",
      groupedTooltip: "Total closed sales",
      changeText: percentChange
    },
    pricePerSqFt: {
      canvas: "sjMlsV3PricePerSqFt",
      snapshot: "sjMlsV3SnapshotPricePerSqFt",
      change: "sjMlsV3ChangePricePerSqFt",
      title: "Price per Square Foot",
      chartType: "line",
      axisTitle: "Price per square foot",
      format: function (number) { return money(number) + "/sq ft"; },
      tick: function (number) { return "$" + Math.round(number); },
      monthlyTooltip: "Price per square foot",
      groupedTooltip: "Average monthly value",
      changeText: percentChange
    }
  };

  function decimal(number, digits) {
    return Number(number).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function money(number) {
    return "$" + Math.round(number).toLocaleString("en-US");
  }

  function compactMoney(number) {
    var absolute = Math.abs(number);
    if (absolute >= 1000000) return "$" + (number / 1000000).toFixed(1) + "M";
    if (absolute >= 1000) return "$" + Math.round(number / 1000) + "K";
    return "$" + Math.round(number);
  }

  function signedNumber(number, digits) {
    var rounded = Number(number.toFixed(digits));
    if (rounded > 0) return "+" + decimal(rounded, digits);
    return decimal(rounded, digits);
  }

  function percentChange(current, prior) {
    return signedNumber(((current / prior) - 1) * 100, 1) + "% year over year";
  }

  function monthLabel(label) {
    var parts = label.split("-");
    return MONTHS[Number(parts[1]) - 1] + " " + parts[0];
  }

  function groupKey(label, selectedResolution) {
    var parts = label.split("-");
    var year = Number(parts[0]);
    var month = Number(parts[1]);
    if (selectedResolution === "monthly") return label;
    if (selectedResolution === "quarterly") return year + "-Q" + Math.ceil(month / 3);
    return String(year);
  }

  function expectedMonths(selectedResolution) {
    if (selectedResolution === "monthly") return 1;
    if (selectedResolution === "quarterly") return 3;
    return 12;
  }

  function displayLabel(key, selectedResolution, partial) {
    if (selectedResolution === "monthly") return monthLabel(key);
    if (selectedResolution === "quarterly") {
      var parts = key.split("-Q");
      return parts[0] + " Q" + parts[1] + (partial ? "*" : "");
    }
    return key + (partial ? " YTD*" : "");
  }

  function aggregateSeries(series, selectedResolution) {
    var groups = [];
    var byKey = {};
    series.labels.forEach(function (label, index) {
      var key = groupKey(label, selectedResolution);
      if (!byKey[key]) {
        byKey[key] = { key: key, labels: [], values: [] };
        groups.push(byKey[key]);
      }
      byKey[key].labels.push(label);
      if (series.values[index] !== null) byKey[key].values.push(series.values[index]);
    });

    return groups.map(function (group) {
      var value = null;
      if (group.values.length) {
        if (series.aggregation === "sum") {
          value = group.values.reduce(function (total, item) { return total + item; }, 0);
        } else {
          value = group.values.reduce(function (total, item) { return total + item; }, 0) / group.values.length;
        }
      }
      var partial = selectedResolution !== "monthly" &&
        group.labels.length < expectedMonths(selectedResolution);
      return {
        label: displayLabel(group.key, selectedResolution, partial),
        value: value,
        partial: partial,
        months: group.labels.length,
        validMonths: group.values.length,
        sourceLabels: group.labels.slice()
      };
    });
  }

  function yearOverYearSalePrice(selectedResolution) {
    var series = DATA.series.salePrice;
    var valueByLabel = {};
    series.labels.forEach(function (label, index) {
      valueByLabel[label] = series.values[index];
    });

    return aggregateSeries(series, selectedResolution).map(function (point) {
      var priorValues = point.sourceLabels.map(function (label) {
        var parts = label.split("-");
        var priorLabel = (Number(parts[0]) - 1) + "-" + parts[1];
        return valueByLabel[priorLabel];
      }).filter(function (value) {
        return value !== null && typeof value !== "undefined";
      });
      var priorAverage = priorValues.length ?
        priorValues.reduce(function (total, value) { return total + value; }, 0) / priorValues.length :
        null;
      point.value = point.value !== null && priorAverage !== null ?
        ((point.value / priorAverage) - 1) * 100 :
        null;
      point.validMonths = Math.min(point.validMonths, priorValues.length);
      return point;
    });
  }

  function pointsForMetric(metricKey) {
    var definition = metricDefinitions[metricKey];
    if (definition.derived === "yearOverYear") return yearOverYearSalePrice(resolution);
    return aggregateSeries(DATA.series[metricKey], resolution);
  }

  var referenceLinePlugin = {
    id: "sjV3ReferenceLine",
    afterDraw: function (chart, args, options) {
      if (!options || typeof options.y !== "number") return;
      var yScale = chart.scales.y;
      var xScale = chart.scales.x;
      if (!yScale || !xScale) return;
      var pixel = yScale.getPixelForValue(options.y);
      var context = chart.ctx;
      context.save();
      context.beginPath();
      context.setLineDash([5, 5]);
      context.strokeStyle = "rgba(212,168,83,0.85)";
      context.lineWidth = 1;
      context.moveTo(xScale.left, pixel);
      context.lineTo(xScale.right, pixel);
      context.stroke();
      context.setLineDash([]);
      if (options.label) {
        context.fillStyle = "#8b6a2d";
        context.font = "10px DM Sans, sans-serif";
        context.textAlign = "right";
        context.fillText(options.label, xScale.right - 3, pixel - 6);
      }
      context.restore();
    }
  };

  function chartOptions(definition) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 350
      },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(30,35,38,0.94)",
          padding: 11,
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          callbacks: {
            label: function (context) {
              var prefix = resolution === "monthly" ?
                definition.monthlyTooltip : definition.groupedTooltip;
              return prefix + ": " + definition.format(context.parsed.y);
            },
            afterLabel: function (context) {
              var point = context.chart.$aggregated[context.dataIndex];
              if (!point) return "";
              if (point.partial && resolution === "yearly") {
                return "Partial year: " + point.months + " months";
              }
              if (point.partial && resolution === "quarterly") {
                return "Partial quarter: " + point.months + " months";
              }
              if (point.validMonths !== point.months) {
                return "Calculated from " + point.validMonths + " valid months";
              }
              return "";
            }
          }
        },
        sjV3ReferenceLine: typeof definition.referenceLine === "number" ?
          { y: definition.referenceLine, label: definition.referenceLabel || "" } : false
      },
      scales: {
        x: {
          title: {
            display: true,
            text: "Year",
            color: "#666",
            font: { size: 11, weight: "normal" }
          },
          grid: { display: false },
          ticks: {
            color: "#777",
            autoSkip: true,
            maxRotation: 0,
            maxTicksLimit: 10,
            font: { size: 10 }
          }
        },
        y: {
          beginAtZero: definition.chartType === "bar",
          title: {
            display: true,
            text: definition.axisTitle,
            color: "#666",
            font: { size: 11, weight: "normal" }
          },
          grid: { color: COLORS.grid },
          ticks: {
            color: "#777",
            maxTicksLimit: 6,
            font: { size: 10 },
            callback: definition.tick
          }
        }
      }
    };
  }

  function pointColors(points) {
    return points.map(function (point) {
      return point.partial ? COLORS.gold : COLORS.teal;
    });
  }

  function barColors(points, definition) {
    return points.map(function (point) {
      if (point.partial) return COLORS.goldFill;
      if (definition.derived === "yearOverYear" && point.value < 0) return COLORS.redFill;
      return definition.derived === "yearOverYear" ? "rgba(44,83,100,0.62)" : COLORS.blueFill;
    });
  }

  function createChart(metricKey) {
    var definition = metricDefinitions[metricKey];
    var canvas = document.getElementById(definition.canvas);
    if (!canvas) return;
    var points = pointsForMetric(metricKey);
    var isBar = definition.chartType === "bar";
    var dataset = {
      label: definition.title,
      data: points.map(function (point) { return point.value; }),
      borderColor: COLORS.teal,
      backgroundColor: isBar ? barColors(points, definition) : COLORS.tealFill,
      borderWidth: isBar ? 1 : 2.5,
      borderRadius: isBar ? 4 : 0,
      pointRadius: isBar ? 0 : 4,
      pointHoverRadius: isBar ? 0 : 6,
      pointBackgroundColor: pointColors(points),
      pointBorderColor: "#ffffff",
      pointBorderWidth: 1.5,
      spanGaps: false,
      fill: false,
      tension: 0.16
    };
    var chart = new Chart(canvas, {
      type: definition.chartType,
      data: {
        labels: points.map(function (point) { return point.label; }),
        datasets: [dataset]
      },
      options: chartOptions(definition),
      plugins: [referenceLinePlugin]
    });
    chart.$aggregated = points;
    charts.push({ metricKey: metricKey, chart: chart });
  }

  function resolutionAxisTitle() {
    if (resolution === "monthly") return "Month";
    if (resolution === "quarterly") return "Quarter";
    return "Year";
  }

  function updateCharts() {
    charts.forEach(function (entry) {
      var definition = metricDefinitions[entry.metricKey];
      var points = pointsForMetric(entry.metricKey);
      var dataset = entry.chart.data.datasets[0];
      entry.chart.$aggregated = points;
      entry.chart.data.labels = points.map(function (point) { return point.label; });
      dataset.data = points.map(function (point) { return point.value; });
      dataset.pointBackgroundColor = pointColors(points);
      if (definition.chartType === "bar") dataset.backgroundColor = barColors(points, definition);
      dataset.pointRadius = definition.chartType === "bar" ? 0 : (resolution === "monthly" ? 0 : 4);
      dataset.pointHoverRadius = definition.chartType === "bar" ? 0 : (resolution === "monthly" ? 4 : 6);
      entry.chart.options.scales.x.title.text = resolutionAxisTitle();
      entry.chart.options.scales.x.ticks.maxTicksLimit = resolution === "monthly" ? 9 : 12;
      entry.chart.update();
    });
  }

  function updateSnapshots() {
    Object.keys(metricDefinitions).forEach(function (metricKey) {
      var definition = metricDefinitions[metricKey];
      if (!definition.snapshot) return;
      var series = DATA.series[metricKey];
      var lastIndex = series.values.length - 1;
      var priorIndex = lastIndex - 12;
      var current = series.values[lastIndex];
      var prior = series.values[priorIndex];
      var valueElement = document.getElementById(definition.snapshot);
      var changeElement = document.getElementById(definition.change);
      if (valueElement) {
        valueElement.textContent = definition.snapshotFormat ?
          definition.snapshotFormat(current) : definition.format(current);
      }
      if (changeElement) changeElement.textContent = definition.changeText(current, prior);
    });
    var latestMonthElement = document.getElementById("sjMlsV3LatestMonth");
    if (latestMonthElement) latestMonthElement.textContent = monthLabel(DATA.metadata.latestMonth);
  }

  function bindControls() {
    var buttons = document.querySelectorAll("[data-sj-mls-resolution]");
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        resolution = button.getAttribute("data-sj-mls-resolution");
        buttons.forEach(function (item) {
          var active = item === button;
          item.classList.toggle("active", active);
          item.setAttribute("aria-pressed", active ? "true" : "false");
        });
        updateCharts();
      });
    });
  }

  Object.keys(metricDefinitions).forEach(createChart);
  bindControls();
  updateSnapshots();
})();
