import { getBudgetSummary, formatMoney } from "../helpers";

export default function BudgetSummary({ plan, selectedFlight, totalBudgetLkr }) {
  const { flightLkr, accomLkr, transportLkr, activitiesLkr, totalLkr } =
    getBudgetSummary(plan, selectedFlight, totalBudgetLkr);

  const rows = [
    { label: "Flights", value: flightLkr, show: flightLkr != null },
    { label: "Accommodation", value: accomLkr, show: accomLkr != null },
    { label: "Transport", value: transportLkr, show: transportLkr != null },
    { label: "Activities", value: activitiesLkr, show: activitiesLkr != null },
  ].filter((r) => r.show);

  const grandTotal = totalLkr;

  return (
    <div className="budget-rows" id="section-budget">
      {rows.map((row) => (
        <div key={row.label} className="budget-row">
          <span className="budget-label">{row.label}</span>
          <span className="budget-amount">{formatMoney(row.value)}</span>
        </div>
      ))}
      {grandTotal && (
        <div className="budget-row total">
          <span className="budget-label">Total</span>
          <span className="budget-amount">{formatMoney(grandTotal)}</span>
        </div>
      )}
      {!rows.length && !grandTotal && (
        <div className="empty-state">Budget details will be available after plan generation.</div>
      )}
    </div>
  );
}
