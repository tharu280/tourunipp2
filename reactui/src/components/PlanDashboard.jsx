import RouteMap from "./RouteMap";
import ItinerarySection from "./ItinerarySection";
import AccommodationSection from "./AccommodationSection";
import FlightSummary from "./FlightSummary";
import BudgetSummary from "./BudgetSummary";
import CrowdIntelligenceSection from "./CrowdIntelligenceSection";
import HeatmapSection from "./HeatmapSection";
import AlertsSection from "./AlertsSection";
import { getOverallConditions, titleCase } from "../helpers";

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
  const passengers = Number(req.flight_passengers || 1);
  const totalBudget = req.total_budget_lkr;

  // Trip header info
  const origin = plan?.origin_resolved?.name || req.origin || "Start";
  const destination = plan?.destination_resolved?.name || req.destination || "Destination";
  const duration = plan?.trip_dates?.length || req.duration || "—";
  const startDate = req.flight_departure_date || plan?.start_date;
  const dateRange = startDate
    ? `${new Date(startDate).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}`
    : "";

  // Conditions
  const conditions = getOverallConditions(plan);

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
          {(duration || dateRange) && (
            <div className="dashboard-nav-sub">
              {duration && `${duration} days`}{duration && dateRange ? " · " : ""}{dateRange}
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
                text: `${origin} → ${destination}, ${duration} days`,
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
        <RouteMap plan={plan} />

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
          <ItinerarySection plan={plan} />
        </Section>

        {/* Accommodation */}
        <Section title="Accommodation" linkText="View all" id="accommodation-section">
          <AccommodationSection plan={plan} />
        </Section>

        {/* Flight */}
        <Section title="Flight" id="flight-section">
          <FlightSummary flight={selectedFlight} passengers={passengers} />
        </Section>

        {/* Budget */}
        <Section title="Budget summary" id="budget-section">
          <BudgetSummary
            plan={plan}
            selectedFlight={selectedFlight}
            totalBudgetLkr={totalBudget}
          />
        </Section>

        {/* Crowd Intelligence */}
        <Section title="Crowd intelligence" id="crowd-section">
          <CrowdIntelligenceSection plan={plan} dashboardData={dashboardData} />
        </Section>

        {/* Heatmaps */}
        <Section title="Pressure heatmaps" id="heatmap-section">
          <HeatmapSection plan={plan} dashboardData={dashboardData} />
        </Section>

        {/* Alerts */}
        <Section title="Alerts &amp; advisories" id="alerts-section">
          <AlertsSection plan={plan} />
        </Section>
      </div>
    </div>
  );
}
