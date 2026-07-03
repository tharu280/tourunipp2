import RouteMap from "./RouteMap";
import ItinerarySection from "./ItinerarySection";
import AccommodationSection from "./AccommodationSection";
import FlightSummary from "./FlightSummary";
import BudgetSummary from "./BudgetSummary";
import CrowdIntelligenceSection from "./CrowdIntelligenceSection";
import HeatmapSection from "./HeatmapSection";
import AlertsSection from "./AlertsSection";
import {
  getOverallConditions,
  mergePlanWithDashboard,
  titleCase,
} from "../helpers";

/* ── SVG Icons ─────────────────────────────────────────────────── */
function IconBack() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function IconShare() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" fill="none">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  );
}

/* ── Condition dot ──────────────────────────────────────────────── */
function conditionClass(level) {
  if (!level) return "unknown";
  const l = String(level).toLowerCase();
  if (l === "low" || l === "good" || l === "clear") return "low";
  if (l === "medium" || l === "moderate") return "medium";
  if (l === "high") return "high";
  return "unknown";
}

function overallClass(label) {
  if (!label) return "";
  const l = label.toLowerCase();
  if (l === "caution") return "caution";
  if (l === "moderate") return "moderate";
  return "";
}

/* ── Section wrapper ─────────────────────────────────────────────── */
function Section({ title, linkText, children, id }) {
  return (
    <section className="d-card" id={id} aria-labelledby={`${id}-title`}>
      <div className="d-card-header">
        <h2 className="d-card-title" id={`${id}-title`}>{title}</h2>
        {linkText && <span className="d-card-link">{linkText}</span>}
      </div>
      <div className="d-card-body" style={{ padding: 0 }}>
        {children}
      </div>
    </section>
  );
}

/* ── Main Dashboard ─────────────────────────────────────────────── */
export default function PlanDashboard({
  plan,
  dashboardData,
  selectedFlight,
  session,
  onReset,
}) {
  const req = session?.trip_requirements || {};
  const viewPlan = mergePlanWithDashboard(plan, dashboardData);
  const viewReq = viewPlan?.trip_requirements || req;
  const passengers = Number(req.flight_passengers || 1);
  const totalBudget =
    viewReq.total_budget_lkr ||
    viewPlan?.budget_summary?.total_budget_lkr ||
    req.total_budget_lkr;

  // Trip header info
  const origin = viewPlan?.origin_resolved?.name || viewReq.origin || "Start";
  const destination =
    viewPlan?.destination_resolved?.name || viewReq.destination || "Destination";
  const tripDates = viewPlan?.trip_dates || viewPlan?.plan_overview?.trip_dates || [];
  const durationValue =
    viewPlan?.plan_overview?.trip_days ||
    (Array.isArray(tripDates) && tripDates.length ? tripDates.length : null);
  const durationLabel =
    durationValue ? `${durationValue} days` : viewReq.duration || "—";
  const startDate =
    tripDates[0] ||
    viewReq.flight_departure_date ||
    viewPlan?.start_date;
  const endDate = tripDates.length > 1 ? tripDates[tripDates.length - 1] : null;
  const dateRange = startDate
    ? `${new Date(startDate).toLocaleDateString("en-US", { day: "numeric", month: "short" })}${
        endDate
          ? ` – ${new Date(endDate).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}`
          : ` ${new Date(startDate).getFullYear()}`
      }`
    : "";

  // Conditions
  const conditions = getOverallConditions(viewPlan);

  return (
    <div className="dashboard-screen" id="screen-dashboard">
      {/* Navigation */}
      <nav className="dashboard-nav">
        <button
          className="dashboard-nav-back"
          onClick={onReset}
          type="button"
          aria-label="Start over"
        >
          <IconBack />
        </button>
        <div className="dashboard-nav-center">
          <div className="dashboard-nav-title">Your trip to Sri Lanka</div>
          {(durationLabel || dateRange) && (
            <div className="dashboard-nav-sub">
              {durationLabel}{durationLabel && dateRange ? " · " : ""}{dateRange}
            </div>
          )}
        </div>
        <button
          className="dashboard-nav-share"
          type="button"
          aria-label="Share"
          onClick={() => {
            if (navigator.share) {
              navigator.share({
                title: "My Sri Lanka Trip — TourUni",
                text: `${origin} → ${destination}, ${durationLabel}`,
                url: window.location.href,
              }).catch(() => {});
            }
          }}
        >
          <IconShare />
        </button>
      </nav>

      <div className="dashboard-content">
        {/* Route Map */}
        <RouteMap plan={viewPlan} />

        {/* Overall Conditions */}
        <div className="conditions-card">
          <div className="conditions-header">
            <span className="conditions-title">Overall conditions</span>
            <span className={`conditions-overall ${overallClass(conditions.overall)}`}>
              {conditions.overall}
            </span>
          </div>
          <div className="conditions-row">
            {[
              { label: "Crowd", value: conditions.crowd },
              { label: "Weather", value: conditions.weather },
              { label: "Roads", value: conditions.roads },
            ].map((c) => (
              <div key={c.label} className="condition-item">
                <div className={`condition-dot ${conditionClass(c.value)}`} aria-hidden="true" />
                <span className="condition-label">{c.label}</span>
                <span className="condition-value">{titleCase(c.value)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Itinerary */}
        <Section title="Itinerary" linkText="View full itinerary" id="itinerary-section">
          <ItinerarySection plan={viewPlan} />
        </Section>

        {/* Accommodation */}
        <Section title="Accommodation" linkText="View all" id="accommodation-section">
          <AccommodationSection plan={viewPlan} />
        </Section>

        {/* Flight */}
        <Section title="Flight" id="flight-section">
          <FlightSummary
            flight={selectedFlight}
            passengers={passengers}
            plan={viewPlan}
          />
        </Section>

        {/* Budget */}
        <Section title="Budget summary" id="budget-section">
          <BudgetSummary
            plan={viewPlan}
            selectedFlight={selectedFlight}
            totalBudgetLkr={totalBudget}
          />
        </Section>

        {/* Crowd Intelligence */}
        <Section title="Crowd intelligence" id="crowd-section">
          <CrowdIntelligenceSection plan={viewPlan} dashboardData={dashboardData} />
        </Section>

        {/* Heatmaps */}
        <Section title="Pressure heatmaps" id="heatmap-section">
          <HeatmapSection plan={viewPlan} dashboardData={dashboardData} />
        </Section>

        {/* Alerts */}
        <Section title="Alerts &amp; advisories" id="alerts-section">
          <AlertsSection plan={viewPlan} />
        </Section>
      </div>
    </div>
  );
}
