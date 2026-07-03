import { getBudgetSummary, formatMoney } from "../helpers";

export default function BudgetSummary({ plan, selectedFlight, totalBudgetLkr }) {
  const { flightLkr, accomLkr, transportLkr, activitiesLkr, totalLkr } =
    getBudgetSummary(plan, selectedFlight, totalBudgetLkr);

  const rows = [
    { label: "Flights", value: flightLkr, show: flightLkr != null, icon: "✈️" },
    { label: "Accommodation", value: accomLkr, show: accomLkr != null, icon: "🏨" },
    { label: "Transport", value: transportLkr, show: transportLkr != null, icon: "🚗" },
    { label: "Activities", value: activitiesLkr, show: activitiesLkr != null, icon: "🎫" },
  ].filter((r) => r.show);

  const grandTotal = totalLkr;
  const budgetRatio = totalBudgetLkr && grandTotal ? Math.min(grandTotal / totalBudgetLkr, 1) : null;
  const budgetPercentage = budgetRatio ? (budgetRatio * 100).toFixed(0) : 0;

  return (
    <div className="budget-rows" id="section-budget">
      {rows.map((row) => (
        <div key={row.label} className="budget-row">
          <span className="budget-label">
            <div className="budget-icon" aria-hidden="true">{row.icon}</div>
            {row.label}
          </span>
          <span className="budget-amount">{formatMoney(row.value)}</span>
        </div>
      ))}
      {grandTotal && (
        <div className="budget-row total">
          <span className="budget-label">Grand Total</span>
          <span className="budget-amount">{formatMoney(grandTotal)}</span>
        </div>
      )}

      {/* ── Budget Progress Bar ── */}
      {totalBudgetLkr > 0 && grandTotal > 0 && (
        <div className="budget-progress-wrap">
          <div className="budget-progress-bar">
            <div 
              className="budget-progress-fill" 
              style={{ width: `${budgetPercentage}%`, backgroundColor: budgetRatio > 0.95 ? '#EF4444' : undefined }}
            />
          </div>
          <div className="budget-progress-label">
            <span>{budgetPercentage}% used</span>
            <span>{formatMoney(Math.max(0, totalBudgetLkr - grandTotal))} remaining</span>
          </div>
        </div>
      )}

      {!rows.length && !grandTotal && (
        <div className="empty-state">Budget details will be available after plan generation.</div>
      )}
    </div>
  );
}
