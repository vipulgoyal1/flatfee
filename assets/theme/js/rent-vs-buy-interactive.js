(function () {
  "use strict";

  const PROJECTION_YEARS = 30;
  const defaults = {
    homePrice: 2000000,
    downPaymentPct: 20,
    taxAdjustedRate: 4.25,
    mortgageTermYears: 30,
    propertyTaxPct: 1.25,
    maintenancePct: 0.7,
    propertyAppreciationPct: 5,
    yearsCompare: 10,
    initialMonthlyRent: 5000,
    annualRentGrowthPct: 5,
    annualInvestmentReturnPct: 9,
    helperMortgageAmount: 1600000,
    helperActualBankRate: 5.5,
    helperFederalStandardDeduction: 32000,
    helperSaltDeduction: 30000,
    helperFederalMarginalTaxRate: 35,
    helperCaliforniaMarginalTaxRate: 11.3
  };

  const mainInputs = {
    homePrice: document.getElementById("homePrice"),
    downPaymentPct: document.getElementById("downPaymentPct"),
    taxAdjustedRate: document.getElementById("taxAdjustedRate"),
    mortgageTermYears: document.getElementById("mortgageTermYears"),
    propertyTaxPct: document.getElementById("propertyTaxPct"),
    maintenancePct: document.getElementById("maintenancePct"),
    propertyAppreciationPct: document.getElementById("propertyAppreciationPct"),
    yearsCompare: document.getElementById("yearsCompare"),
    initialMonthlyRent: document.getElementById("initialMonthlyRent"),
    annualRentGrowthPct: document.getElementById("annualRentGrowthPct"),
    annualInvestmentReturnPct: document.getElementById("annualInvestmentReturnPct")
  };

  const helperInputs = {
    helperMortgageAmount: document.getElementById("helperMortgageAmount"),
    helperActualBankRate: document.getElementById("helperActualBankRate"),
    helperFederalStandardDeduction: document.getElementById("helperFederalStandardDeduction"),
    helperSaltDeduction: document.getElementById("helperSaltDeduction"),
    helperFederalMarginalTaxRate: document.getElementById("helperFederalMarginalTaxRate"),
    helperCaliforniaMarginalTaxRate: document.getElementById("helperCaliforniaMarginalTaxRate")
  };

  const outputs = {
    loanAmountOutput: document.getElementById("loanAmountOutput"),
    monthlyPaymentOutput: document.getElementById("monthlyPaymentOutput"),
    helperAnnualInterest: document.getElementById("helperAnnualInterest"),
    helperDeductibleFederal: document.getElementById("helperDeductibleFederal"),
    helperNetItemized: document.getElementById("helperNetItemized"),
    helperFederalTaxSavings: document.getElementById("helperFederalTaxSavings"),
    helperDeductibleCA: document.getElementById("helperDeductibleCA"),
    helperCATaxSavings: document.getElementById("helperCATaxSavings"),
    helperTotalTaxSavings: document.getElementById("helperTotalTaxSavings"),
    helperAfterTaxInterest: document.getElementById("helperAfterTaxInterest"),
    helperEffectiveRate: document.getElementById("helperEffectiveRate"),
    summaryBuy: document.getElementById("summaryBuy"),
    summaryRent: document.getElementById("summaryRent"),
    summaryDiff: document.getElementById("summaryDiff"),
    summaryOption: document.getElementById("summaryOption"),
    projectionInfo: document.getElementById("projectionInfo")
  };

  const projectionBody = document.getElementById("projectionBody");
  const helperSyncMortgageAmount = document.getElementById("helperSyncMortgageAmount");
  const applyEffectiveRateButton = document.getElementById("applyEffectiveRate");
  const resetDefaultsButton = document.getElementById("resetDefaults");

  if (!projectionBody) {
    return;
  }

  const currency0 = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  });
  const currency2 = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const percent2 = new Intl.NumberFormat("en-US", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  let latestEffectiveRatePct = defaults.taxAdjustedRate;

  function asNumber(value, fallback) {
    const next = Number(value);
    return Number.isFinite(next) ? next : fallback;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function normalize(value) {
    return Math.abs(value) < 0.000001 ? 0 : value;
  }

  function getMainValues() {
    return {
      homePrice: Math.max(0, asNumber(mainInputs.homePrice.value, defaults.homePrice)),
      downPaymentPct: clamp(asNumber(mainInputs.downPaymentPct.value, defaults.downPaymentPct), 0, 100),
      taxAdjustedRate: asNumber(mainInputs.taxAdjustedRate.value, defaults.taxAdjustedRate),
      mortgageTermYears: clamp(Math.round(asNumber(mainInputs.mortgageTermYears.value, defaults.mortgageTermYears)), 1, 50),
      propertyTaxPct: asNumber(mainInputs.propertyTaxPct.value, defaults.propertyTaxPct),
      maintenancePct: asNumber(mainInputs.maintenancePct.value, defaults.maintenancePct),
      propertyAppreciationPct: asNumber(mainInputs.propertyAppreciationPct.value, defaults.propertyAppreciationPct),
      yearsCompare: clamp(Math.round(asNumber(mainInputs.yearsCompare.value, defaults.yearsCompare)), 0, PROJECTION_YEARS),
      initialMonthlyRent: Math.max(0, asNumber(mainInputs.initialMonthlyRent.value, defaults.initialMonthlyRent)),
      annualRentGrowthPct: asNumber(mainInputs.annualRentGrowthPct.value, defaults.annualRentGrowthPct),
      annualInvestmentReturnPct: asNumber(mainInputs.annualInvestmentReturnPct.value, defaults.annualInvestmentReturnPct)
    };
  }

  function getHelperValues() {
    return {
      helperMortgageAmount: Math.max(0, asNumber(helperInputs.helperMortgageAmount.value, defaults.helperMortgageAmount)),
      helperActualBankRate: asNumber(helperInputs.helperActualBankRate.value, defaults.helperActualBankRate),
      helperFederalStandardDeduction: Math.max(0, asNumber(helperInputs.helperFederalStandardDeduction.value, defaults.helperFederalStandardDeduction)),
      helperSaltDeduction: Math.max(0, asNumber(helperInputs.helperSaltDeduction.value, defaults.helperSaltDeduction)),
      helperFederalMarginalTaxRate: asNumber(helperInputs.helperFederalMarginalTaxRate.value, defaults.helperFederalMarginalTaxRate),
      helperCaliforniaMarginalTaxRate: asNumber(helperInputs.helperCaliforniaMarginalTaxRate.value, defaults.helperCaliforniaMarginalTaxRate)
    };
  }

  function computeMonthlyPayment(loanAmount, annualRatePct, termYears) {
    const months = termYears * 12;
    if (months <= 0) return 0;
    const monthlyRate = annualRatePct / 1200;
    if (Math.abs(monthlyRate) < 1e-12) return loanAmount / months;
    return loanAmount * monthlyRate / (1 - Math.pow(1 + monthlyRate, -months));
  }

  function computeRemainingLoan(loanAmount, monthlyPayment, annualRatePct, monthsElapsed) {
    const monthlyRate = annualRatePct / 1200;
    if (monthsElapsed <= 0) return loanAmount;
    if (Math.abs(monthlyRate) < 1e-12) return loanAmount - monthlyPayment * monthsElapsed;
    const growth = Math.pow(1 + monthlyRate, monthsElapsed);
    return loanAmount * growth - monthlyPayment * ((growth - 1) / monthlyRate);
  }

  function computeHelper(helperValues) {
    const mortgageAmount = helperValues.helperMortgageAmount;
    const actualRate = helperValues.helperActualBankRate;
    const annualInterest = mortgageAmount * actualRate / 100;
    const deductibleFederal = Math.min(mortgageAmount, 750000) * actualRate / 100;
    const netItemized = Math.max(0, deductibleFederal + helperValues.helperSaltDeduction - helperValues.helperFederalStandardDeduction);
    const federalTaxSavings = netItemized * helperValues.helperFederalMarginalTaxRate / 100;
    const deductibleCA = Math.min(mortgageAmount, 1000000) * actualRate / 100;
    const caTaxSavings = deductibleCA * helperValues.helperCaliforniaMarginalTaxRate / 100;
    const totalTaxSavings = federalTaxSavings + caTaxSavings;
    const afterTaxInterest = annualInterest - totalTaxSavings;
    const effectiveRatePct = mortgageAmount === 0 ? 0 : (afterTaxInterest / mortgageAmount) * 100;

    return {
      annualInterest: normalize(annualInterest),
      deductibleFederal: normalize(deductibleFederal),
      netItemized: normalize(netItemized),
      federalTaxSavings: normalize(federalTaxSavings),
      deductibleCA: normalize(deductibleCA),
      caTaxSavings: normalize(caTaxSavings),
      totalTaxSavings: normalize(totalTaxSavings),
      afterTaxInterest: normalize(afterTaxInterest),
      effectiveRatePct: normalize(effectiveRatePct)
    };
  }

  function computeProjection(mainValues) {
    const rows = [];
    const loanAmount = mainValues.homePrice - (mainValues.downPaymentPct / 100) * mainValues.homePrice;
    const monthlyMortgagePayment = computeMonthlyPayment(loanAmount, mainValues.taxAdjustedRate, mainValues.mortgageTermYears);
    const annualMortgagePayment = monthlyMortgagePayment * 12;
    const downPaymentAmount = mainValues.downPaymentPct * mainValues.homePrice / 100;

    let propertyValue = mainValues.homePrice;
    let annualRent = mainValues.initialMonthlyRent * 12;
    let stockBalance = downPaymentAmount;

    rows.push({
      year: 0,
      propertyValue,
      loanRemaining: loanAmount,
      homeEquity: propertyValue - loanAmount,
      annualMortgagePayment: 0,
      taxMaintenanceInsurance: null,
      cashOutflowBuying: null,
      annualRent,
      costDifference: null,
      stockContribution: null,
      stockBalance
    });

    for (let year = 1; year <= PROJECTION_YEARS; year += 1) {
      propertyValue *= 1 + mainValues.propertyAppreciationPct / 100;
      const loanRemaining = computeRemainingLoan(loanAmount, monthlyMortgagePayment, mainValues.taxAdjustedRate, year * 12);
      const homeEquity = propertyValue - loanRemaining;
      const taxMaintenanceInsurance =
        propertyValue * mainValues.maintenancePct / 100 +
        Math.pow(1.02, year) * mainValues.homePrice * mainValues.propertyTaxPct / 100;
      const cashOutflowBuying = annualMortgagePayment + taxMaintenanceInsurance;
      annualRent *= 1 + mainValues.annualRentGrowthPct / 100;
      const costDifference = cashOutflowBuying - annualRent;
      const stockContribution = costDifference > 0 ? costDifference : 0;
      stockBalance = stockBalance * (1 + mainValues.annualInvestmentReturnPct / 100) + stockContribution;

      rows.push({
        year,
        propertyValue: normalize(propertyValue),
        loanRemaining: normalize(loanRemaining),
        homeEquity: normalize(homeEquity),
        annualMortgagePayment: normalize(annualMortgagePayment),
        taxMaintenanceInsurance: normalize(taxMaintenanceInsurance),
        cashOutflowBuying: normalize(cashOutflowBuying),
        annualRent: normalize(annualRent),
        costDifference: normalize(costDifference),
        stockContribution: normalize(stockContribution),
        stockBalance: normalize(stockBalance)
      });
    }

    return {
      loanAmount: normalize(loanAmount),
      monthlyMortgagePayment: normalize(monthlyMortgagePayment),
      rows
    };
  }

  function formatCurrency(value) {
    return currency0.format(value);
  }

  function formatOptionalCurrency(value) {
    if (value === null || typeof value === "undefined") return "\u2014";
    return formatCurrency(value);
  }

  function renderTable(rows) {
    projectionBody.innerHTML = rows.map(function (row) {
      return [
        "<tr>",
        "<td>", row.year, "</td>",
        "<td>", formatCurrency(row.propertyValue), "</td>",
        "<td>", formatCurrency(row.loanRemaining), "</td>",
        "<td>", formatCurrency(row.homeEquity), "</td>",
        "<td>", formatOptionalCurrency(row.annualMortgagePayment), "</td>",
        "<td>", formatOptionalCurrency(row.taxMaintenanceInsurance), "</td>",
        "<td>", formatOptionalCurrency(row.cashOutflowBuying), "</td>",
        "<td>", formatCurrency(row.annualRent), "</td>",
        "<td>", formatOptionalCurrency(row.costDifference), "</td>",
        "<td>", formatOptionalCurrency(row.stockContribution), "</td>",
        "<td>", formatCurrency(row.stockBalance), "</td>",
        "</tr>"
      ].join("");
    }).join("");
  }

  function recalculate() {
    const mainValues = getMainValues();
    const projection = computeProjection(mainValues);

    if (helperSyncMortgageAmount.checked) {
      helperInputs.helperMortgageAmount.disabled = true;
      helperInputs.helperMortgageAmount.value = projection.loanAmount.toFixed(2);
    } else {
      helperInputs.helperMortgageAmount.disabled = false;
    }

    const helperValues = getHelperValues();
    const helperResults = computeHelper(helperValues);
    latestEffectiveRatePct = helperResults.effectiveRatePct;

    outputs.loanAmountOutput.textContent = formatCurrency(projection.loanAmount);
    outputs.monthlyPaymentOutput.textContent = currency2.format(projection.monthlyMortgagePayment);

    outputs.helperAnnualInterest.textContent = formatCurrency(helperResults.annualInterest);
    outputs.helperDeductibleFederal.textContent = formatCurrency(helperResults.deductibleFederal);
    outputs.helperNetItemized.textContent = formatCurrency(helperResults.netItemized);
    outputs.helperFederalTaxSavings.textContent = formatCurrency(helperResults.federalTaxSavings);
    outputs.helperDeductibleCA.textContent = formatCurrency(helperResults.deductibleCA);
    outputs.helperCATaxSavings.textContent = formatCurrency(helperResults.caTaxSavings);
    outputs.helperTotalTaxSavings.textContent = formatCurrency(helperResults.totalTaxSavings);
    outputs.helperAfterTaxInterest.textContent = formatCurrency(helperResults.afterTaxInterest);
    outputs.helperEffectiveRate.textContent = percent2.format(helperResults.effectiveRatePct / 100);

    const summaryRow = projection.rows[mainValues.yearsCompare];
    const netWealthBuy = summaryRow.homeEquity;
    const netWealthRent = summaryRow.stockBalance;
    const difference = netWealthBuy - netWealthRent;
    const betterOption = difference > 0 ? "Buying" : "Renting";

    outputs.summaryBuy.textContent = formatCurrency(netWealthBuy);
    outputs.summaryRent.textContent = formatCurrency(netWealthRent);
    outputs.summaryDiff.textContent = formatCurrency(difference);
    outputs.summaryOption.textContent = betterOption;
    outputs.summaryOption.className = difference > 0 ? "rb-pill rb-pill-buy" : "rb-pill rb-pill-rent";
    outputs.projectionInfo.textContent = "Summary uses year " + mainValues.yearsCompare + " (editable in the inputs).";

    renderTable(projection.rows);
  }

  function applyDefaults() {
    Object.keys(mainInputs).forEach(function (key) {
      mainInputs[key].value = defaults[key];
    });
    Object.keys(helperInputs).forEach(function (key) {
      helperInputs[key].value = defaults[key];
    });
    helperSyncMortgageAmount.checked = true;
    recalculate();
  }

  Object.values(mainInputs).forEach(function (input) {
    input.addEventListener("input", recalculate);
  });
  Object.values(helperInputs).forEach(function (input) {
    input.addEventListener("input", recalculate);
  });
  helperSyncMortgageAmount.addEventListener("change", recalculate);

  applyEffectiveRateButton.addEventListener("click", function () {
    mainInputs.taxAdjustedRate.value = latestEffectiveRatePct.toFixed(6);
    recalculate();
  });
  resetDefaultsButton.addEventListener("click", applyDefaults);

  applyDefaults();
})();
