export default function LoadingState({ title, detail, steps = [] }) {
  return (
    <main className="loading-screen" id="screen-loading">
      <div className="loading-spinner-wrap">
        <div className="loading-spinner" role="status" aria-label="Loading" />
      </div>
      <h1 className="loading-title">{title}</h1>
      <p className="loading-detail">{detail}</p>
      {steps.length > 0 && (
        <div className="loading-steps" aria-label="Loading steps">
          {steps.map((step, i) => (
            <span key={i} className="loading-step">{step}</span>
          ))}
        </div>
      )}
    </main>
  );
}
